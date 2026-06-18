"""
generators/extract_products.py
SCRIPT 2 de 3 — Extrae productos por keyword usando búsqueda de texto VTEX.

Lee data/category_trees/category_keywords.json (generado por discover_categories.py)
Para cada tienda, itera sus keywords y busca:
  GET {store}/api/catalog_system/pub/products/search?ft={keyword}&_from=0&_to=49

Guarda productos RAW (sin deduplicar todavía) en:
  data/raw_extraction/{store_slug}.json

La deduplicación por EAN se hace en el script 3 (dedupe_and_build.py).
"""

import json
import time
from pathlib import Path
from urllib.parse import quote

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm

from config import settings

# ─────────────────────────────────────────────
# Config — paths y rate limit centralizados en settings.py
# ─────────────────────────────────────────────
KEYWORDS_PATH = settings.CATEGORY_KEYWORDS_PATH
OUTPUT_DIR    = settings.RAW_EXTRACTION_DIR

PAGE_SIZE            = settings.VTEX_PAGE_SIZE   # _from=0&_to=49 = 50 productos
MAX_PRODUCTS_PER_KW  = 50   # una sola página por keyword — suficiente para la prueba
REQUESTS_PER_SECOND  = settings.VTEX_REQUESTS_PER_SECOND


def _store_slug(store_url: str) -> str:
    return store_url.replace("https://", "").replace("www.", "").split(".")[0]


def slim_product(raw: dict) -> dict:
    """
    Reduce un producto VTEX crudo a solo los campos que necesitamos.

    El JSON original trae 'Installments' y 'PaymentOptions' con decenas de
    métodos de pago × cuotas (eso es lo que infla cada producto a varios KB).
    También descartamos SkuData/ProductData (metadata interna de VTEX) y
    descripciones largas — no aportan nada al análisis de catálogo/ventas.

    Sí conservamos:
      - clusterHighlights: promociones/campañas activas sobre el producto
      - specifications: atributos reales del producto (ej. "Tipo de Producto",
        "Origen"), reconstruidos desde allSpecifications + sus valores
    """
    items = raw.get("items") or [{}]
    item0 = items[0] if items else {}

    sellers = item0.get("sellers") or [{}]
    seller0 = sellers[0] if sellers else {}
    offer   = seller0.get("commertialOffer") or {}

    images = item0.get("images") or []
    first_image_url = images[0].get("imageUrl") if images else None

    categories = raw.get("categories") or []
    category_path = categories[0] if categories else None

    # allSpecifications es solo la lista de NOMBRES; el valor real está en
    # una key dinámica al nivel raíz del producto con ese mismo nombre.
    # Esto excluye automáticamente metadata interna como "ProductData",
    # "SkuData" o "Gr Especificaciones de Producto" si no aparecen listadas
    # como specs reales (VTEX las mete ahí, pero no son atributos de producto).
    spec_names = raw.get("allSpecifications") or []
    specifications = {
        name: raw.get(name)
        for name in spec_names
        if raw.get(name) not in (None, [], "")
    }

    return {
        "productId":          raw.get("productId"),
        "productName":        raw.get("productName"),
        "brand":               raw.get("brand"),
        "productReference":    raw.get("productReference"),
        "categoryId":          raw.get("categoryId"),
        "categoryPath":        category_path,
        "linkText":            raw.get("linkText"),
        "ean":                 item0.get("ean"),
        "imageUrl":            first_image_url,
        "price":               offer.get("Price"),
        "listPrice":           offer.get("ListPrice"),
        "availableQuantity":   offer.get("AvailableQuantity"),
        "isAvailable":         offer.get("IsAvailable"),
        "clusterHighlights":   raw.get("clusterHighlights") or {},
        "specifications":      specifications,
        "_source_store":       raw.get("_source_store"),
        "_source_keyword":     raw.get("_source_keyword"),
    }


class VTEXSearchClient:
    """Cliente HTTP simple para búsqueda por texto VTEX."""

    def __init__(self) -> None:
        self._min_interval = 1.0 / REQUESTS_PER_SECOND
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; DataPipeline/1.0)",
            "Accept": "application/json",
        })

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        sleep = self._min_interval - elapsed
        if sleep > 0:
            time.sleep(sleep)
        self._last_request = time.monotonic()

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def search(self, store_url: str, keyword: str, from_: int = 0, to_: int = PAGE_SIZE) -> list[dict]:
        self._wait()
        # VTEX requiere %20 para espacios en `ft=` — algunas tiendas (ej. Sony)
        # rechazan el '+' que requests genera por defecto en params encoded.
        encoded_kw = quote(keyword, safe="")
        url = f"{store_url}/api/catalog_system/pub/products/search?ft={encoded_kw}&_from={from_}&_to={to_}"
        resp = self.session.get(url, timeout=15)
        if resp.status_code in (204, 206):
            return []
        resp.raise_for_status()
        try:
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


def load_keyword_config(path: Path = KEYWORDS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero discover_categories.py")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_store(client: VTEXSearchClient, store_config: dict) -> list[dict]:
    """
    Itera todas las keywords de una tienda y acumula productos RAW.
    No deduplica aquí — eso lo hace el script 3 via EAN.
    """
    store_url = store_config["url"]
    keywords  = store_config["keywords"]
    slug      = _store_slug(store_url)

    all_products: list[dict] = []

    for kw in tqdm(keywords, desc=f"  {slug}", unit="kw", leave=False):
        try:
            results = client.search(store_url, kw)
        except Exception as e:
            logger.warning(f"  [{slug}] error buscando '{kw}': {e}")
            continue

        # Adjuntamos metadata de origen antes de filtrar campos
        for p in results:
            p["_source_store"] = store_url
            p["_source_keyword"] = kw

        slimmed = [slim_product(p) for p in results]
        all_products.extend(slimmed)

    logger.info(f"[{slug}] {len(all_products)} productos crudos (sin deduplicar) de {len(keywords)} keywords")
    return all_products


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_keyword_config()
    client = VTEXSearchClient()

    total = 0
    for store_config in config:
        store_url = store_config["url"]
        slug = _store_slug(store_url)

        logger.info(f"═══ Extrayendo {slug} ═══")
        products = extract_store(client, store_config)

        out_path = OUTPUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
        logger.success(f"[{slug}] guardado → {out_path} ({len(products)} productos crudos)")

        total += len(products)

    logger.success(f"TOTAL crudo (sin deduplicar): {total:,} productos en {len(config)} tiendas")


if __name__ == "__main__":
    run()