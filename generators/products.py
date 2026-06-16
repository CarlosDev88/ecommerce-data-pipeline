"""
generators/products.py
Cliente VTEX multi-tienda — extrae catálogo real de Colombia.

Fuentes:
  Electrónica  → Jumbo + Sony + Electrolux + Whirlpool
  Ropa y Moda  → Arturo Calle + Studio F + Totto + Mario Hernández + Jumbo
  Hogar        → Jumbo + Electrolux + Whirlpool
  Deportes     → Nike + Asics + Jumbo + Olímpica
  Belleza      → Jumbo + Olímpica
  Juguetes     → Pepe Ganga + Jumbo + Olímpica

Estrategia: fq=C:{category_id}
  → Trae TODO el inventario de una categoría VTEX sin filtros de keyword
  → Mucho más eficiente y diverso que buscar por keyword
"""

import time
from typing import Optional

import pandas as pd
import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm

from config import settings
from models.product import Product
from storage.base import Storage


# ══════════════════════════════════════════════════════════════════════════════
# VTEX CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class VTEXClient:
    """Cliente HTTP para APIs públicas VTEX — sin autenticación requerida."""

    def __init__(self) -> None:
        self._min_interval = 1.0 / settings.VTEX_REQUESTS_PER_SECOND
        self._last_request: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; DataPipeline/1.0)",
            "Accept":     "application/json",
        })

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        sleep   = self._min_interval - elapsed
        if sleep > 0:
            time.sleep(sleep)
        self._last_request = time.monotonic()

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def search(
        self,
        store_url: str,
        category_id: int,
        from_: int,
        to_: int,
    ) -> list[dict]:
        """
        GET /api/catalog_system/pub/products/search?fq=C:{id}&_from=N&_to=M
        Retorna lista de productos o [] si no hay más resultados.
        """
        self._wait()
        url  = f"{store_url}/api/catalog_system/pub/products/search"
        resp = self.session.get(
            url,
            params={"fq": f"C:{category_id}", "_from": from_, "_to": to_},
            timeout=15,
        )
        if resp.status_code in (204, 206):
            return []
        resp.raise_for_status()
        try:
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


# ══════════════════════════════════════════════════════════════════════════════
# PARSER — normaliza JSON VTEX → dataclass Product
# ══════════════════════════════════════════════════════════════════════════════

def parse_vtex_product(
    raw: dict,
    category_name: str,
    store_url: str,
) -> Optional[Product]:
    try:
        product_id = str(raw.get("productId", ""))
        title      = raw.get("productName") or raw.get("productTitle", "")
        if not product_id or not title:
            return None

        # ID único — prefijo de tienda + productId evita colisiones entre tiendas
        store_slug = (
            store_url
            .replace("https://", "")
            .replace("www.", "")
            .split(".")[0]
            .upper()
        )
        item_id = f"{store_slug}-{product_id}"

        # Precio desde items[0].sellers[0].commertialOffer
        price_cop      = 0.0
        original_price: Optional[float] = None
        available_qty  = 0

        items = raw.get("items", [])
        if items:
            seller = (items[0].get("sellers") or [{}])[0]
            offer  = seller.get("commertialOffer", {})
            price_cop      = float(offer.get("Price") or 0)
            original_price = float(offer.get("ListPrice") or 0) or None
            available_qty  = int(offer.get("AvailableQuantity") or 0)

        if price_cop <= 0:
            return None

        # Descuento
        discount_pct: Optional[float] = None
        if original_price and original_price > price_cop:
            discount_pct   = round((original_price - price_cop) / original_price, 4)
        else:
            original_price = None

        # Imágenes (hasta 3)
        pictures: list[str] = []
        if items:
            for img in (items[0].get("images") or [])[:3]:
                url = img.get("imageUrl")
                if url:
                    pictures.append(url)

        link_text = raw.get("linkText", "")
        permalink = f"{store_url}/{link_text}/p" if link_text else None

        return Product(
            item_id             = item_id,
            title               = title,
            category_id         = str(raw.get("categoryId", "")),
            category_name       = category_name,
            status              = "active",
            price_cop           = price_cop,
            original_price_cop  = original_price,
            discount_pct        = discount_pct,
            currency_id         = "COP",
            available_quantity  = available_qty,
            sold_quantity       = 0,
            listing_type_id     = "vtex",
            seller_id           = 0,
            seller_nickname     = store_slug.lower(),
            seller_city         = None,
            seller_state        = None,
            free_shipping       = price_cop >= 150_000,
            logistic_type       = "vtex_fulfillment",
            accepts_mercadopago = False,
            brand               = raw.get("brand") or raw.get("brandName"),
            model               = None,
            color               = None,
            size                = None,
            gtin                = raw.get("productReference"),
            rating_average      = None,
            ratings_total       = None,
            thumbnail_url       = pictures[0] if pictures else None,
            picture_urls        = pictures,
            permalink           = permalink,
            date_created        = None,
            last_updated        = None,
        )
    except Exception as e:
        logger.warning(f"Error parseando {raw.get('productId')} de {store_url}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class ProductGenerator:
    """
    Extrae catálogo multi-tienda VTEX Colombia.

    Por cada categoría en settings.VTEX_CATEGORIES:
      → Itera sus fuentes (tiendas + category_ids)
      → Pagina con fq=C:{id} hasta alcanzar el target
      → Deduplica globalmente por item_id
      → Persiste como Parquet
    """

    def __init__(self, client: VTEXClient, storage: Storage) -> None:
        self.client  = client
        self.storage = storage

    def run(self) -> pd.DataFrame:
        all_products: list[Product] = []
        seen_ids: set[str]          = set()

        for category_name, config in settings.VTEX_CATEGORIES.items():
            target = config["target"]
            n_src  = len(config["sources"])
            logger.info(f"[{category_name}] objetivo: {target:,} | fuentes: {n_src}")

            products = self._extract_category(category_name, config, target, seen_ids)
            all_products.extend(products)
            seen_ids.update(p.item_id for p in products)

            logger.success(f"[{category_name}] ✓ {len(products):,} productos")

        logger.info(f"Total extraído: {len(all_products):,} productos")

        df = pd.DataFrame([p.to_dict() for p in all_products])
        df = self._clean(df)

        self.storage.save(df, settings.PATHS["products"])
        logger.success(f"products.parquet guardado — {len(df):,} filas")
        return df

    # ── Extracción por categoría ────────────────────────────────────────────
    def _extract_category(
        self,
        category_name: str,
        config: dict,
        target: int,
        global_seen: set[str],
    ) -> list[Product]:
        products: list[Product] = []
        local_seen = set(global_seen)
        sources    = config["sources"]

        for source in sources:
            if len(products) >= target:
                break

            store   = source["store"]
            cat_ids = source["category_ids"]

            for cat_id in cat_ids:
                if len(products) >= target:
                    break
                remaining = target - len(products)
                # Cada category_id puede aportar hasta `remaining` productos
                # No limitamos por fuente — dejamos que cada una aporte lo que pueda
                chunk = self._paginate(
                    store         = store,
                    category_id   = cat_id,
                    category_name = category_name,
                    limit         = remaining,
                    seen_ids      = local_seen,
                )
                products.extend(chunk)
                local_seen.update(p.item_id for p in chunk)
                logger.debug(f"  {store.split('//')[1].split('.')[0]} C:{cat_id} → {len(chunk)} productos")

        return products[:target]

    # ── Paginación fq=C:{id} ────────────────────────────────────────────────
    def _paginate(
        self,
        store: str,
        category_id: int,
        category_name: str,
        limit: int,
        seen_ids: set[str],
    ) -> list[Product]:
        products: list[Product] = []
        page_size  = settings.VTEX_PAGE_SIZE   # 49 items por página
        from_      = 0
        store_name = store.replace("https://", "").replace("www.", "").split(".")[0]

        with tqdm(
            total   = limit,
            desc    = f"  {store_name:<18} C:{category_id}",
            unit    = "items",
            leave   = False,
        ) as pbar:
            while len(products) < limit:
                to_ = from_ + page_size - 1
                try:
                    results = self.client.search(store, category_id, from_, to_)
                except Exception as e:
                    logger.warning(f"{store_name} C:{category_id} offset={from_}: {e}")
                    break

                if not results:
                    break  # Sin más productos en esta categoría

                added = 0
                for raw in results:
                    p = parse_vtex_product(raw, category_name, store)
                    if p and p.item_id not in seen_ids:
                        products.append(p)
                        seen_ids.add(p.item_id)
                        added += 1
                        if len(products) >= limit:
                            break

                pbar.update(added)

                # Si la página está incompleta → no hay más
                if len(results) < page_size:
                    break
                from_ += page_size

        return products

    # ── Limpieza final ──────────────────────────────────────────────────────
    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df.drop_duplicates(subset=["item_id"])
        df = df[df["price_cop"] > 0]
        df = df[df["title"].str.len() > 3]

        df["price_cop"]          = df["price_cop"].astype(float)
        df["original_price_cop"] = pd.to_numeric(df["original_price_cop"], errors="coerce")
        df["discount_pct"]       = pd.to_numeric(df["discount_pct"],       errors="coerce")
        df["available_quantity"] = df["available_quantity"].astype(int)
        df["free_shipping"]      = df["free_shipping"].astype(bool)

        logger.info(f"Limpieza: {before:,} → {len(df):,} productos válidos")
        return df


# ══════════════════════════════════════════════════════════════════════════════
# FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def build_product_generator(storage: Storage) -> ProductGenerator:
    return ProductGenerator(client=VTEXClient(), storage=storage)