"""
generators/dedupe_and_build.py
SCRIPT 3 de 3 — Deduplica por EAN y construye el products.parquet final.

Lee todos los data/raw_extraction/{tienda}.json (productos slim, generados
por extract_products.py), deduplica por EAN entre TODAS las tiendas, y
construye el Product final (models/product.py) para persistir como Parquet.

Regla de deduplicación: el EAN es el estándar de industria para identificar
el mismo producto físico sin importar quién lo vende. Si dos productos
(misma tienda o tiendas distintas) comparten EAN, se conserva solo uno —
el primero visto, en el orden en que se procesan los archivos.

Productos sin EAN se conservan todos (no hay forma de deduplicarlos sin
esa clave), pero quedan marcados aparte en las métricas para visibilidad.
"""

import json
from collections import Counter

import pandas as pd
from loguru import logger

from config import settings
from models.product import Product
from storage.local import LocalStorage


def load_all_raw_products() -> list[dict]:
    """Lee y concatena todos los JSON de data/raw_extraction/."""
    raw_dir = settings.RAW_EXTRACTION_DIR

    if not raw_dir.exists():
        raise FileNotFoundError(f"No existe {raw_dir} — corre primero extract_products.py")

    files = sorted(raw_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No hay archivos .json en {raw_dir} — corre primero extract_products.py")

    all_raw: list[dict] = []
    for f in files:
        products = json.loads(f.read_text(encoding="utf-8"))
        logger.info(f"[{f.stem}] {len(products)} productos crudos cargados")
        all_raw.extend(products)

    logger.info(f"Total cargado: {len(all_raw):,} productos de {len(files)} tiendas")
    return all_raw


def dedupe_by_ean(raw_products: list[dict]) -> tuple[list[dict], dict]:
    """
    Deduplica por EAN — primero visto, gana.
    Productos sin EAN se conservan todos (no se pueden deduplicar entre sí).

    Retorna (productos_deduplicados, metricas).
    """
    seen_eans: set[str] = set()
    deduped: list[dict] = []

    n_without_ean = 0
    n_duplicates  = 0

    for p in raw_products:
        ean = p.get("ean")

        if not ean:
            # Sin EAN no hay clave de dedup — se conserva siempre
            deduped.append(p)
            n_without_ean += 1
            continue

        if ean in seen_eans:
            n_duplicates += 1
            continue

        seen_eans.add(ean)
        deduped.append(p)

    metrics = {
        "raw_total":        len(raw_products),
        "deduped_total":    len(deduped),
        "duplicates_removed": n_duplicates,
        "without_ean":      n_without_ean,
        "unique_eans":      len(seen_eans),
    }
    return deduped, metrics


def build_products(deduped: list[dict]) -> list[Product]:
    """Construye Product tipado para cada dict slim sobreviviente."""
    products: list[Product] = []
    n_errors = 0

    for slim in deduped:
        try:
            products.append(Product.from_slim(slim))
        except Exception as e:
            n_errors += 1
            logger.warning(f"Error construyendo Product de {slim.get('productId')}: {e}")

    if n_errors:
        logger.warning(f"{n_errors} productos descartados por error de construcción")

    return products


def summarize_by_store_and_category(products: list[Product]) -> None:
    """Loggea conteos finales por tienda y por categoría para verificación rápida."""
    by_store    = Counter(p.source_store for p in products)
    by_category = Counter(p.category_path or "(sin categoría)" for p in products)

    logger.info("── Productos finales por tienda ──")
    for store, count in by_store.most_common():
        slug = store.replace("https://", "").replace("www.", "").split(".")[0]
        logger.info(f"  {slug:<18} {count:>5,}")

    logger.info("── Top 10 categorías por volumen ──")
    for category, count in by_category.most_common(10):
        logger.info(f"  {count:>5,}  {category}")


def run() -> None:
    raw_products = load_all_raw_products()

    deduped, metrics = dedupe_by_ean(raw_products)
    logger.success(
        f"Dedup EAN: {metrics['raw_total']:,} crudos → {metrics['deduped_total']:,} finales "
        f"({metrics['duplicates_removed']:,} duplicados eliminados, "
        f"{metrics['without_ean']:,} sin EAN conservados, "
        f"{metrics['unique_eans']:,} EAN únicos)"
    )

    products = build_products(deduped)
    logger.success(f"{len(products):,} Product construidos")

    summarize_by_store_and_category(products)

    df = pd.DataFrame([p.to_dict() for p in products])

    storage = LocalStorage()
    storage.save(df, settings.PATHS["products"])
    logger.success(f"products.parquet guardado — {len(df):,} filas")


if __name__ == "__main__":
    run()