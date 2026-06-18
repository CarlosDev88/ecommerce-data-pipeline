"""
generators/discover_categories.py
SCRIPT 1 de 3 — Descubre categorías nivel 1 de cada tienda VTEX.

Para cada tienda, trae las categorías raíz y sus primeros N hijos directos,
extrae solo los `name` (no IDs) y los guarda como keywords de búsqueda.

Tiendas y tamaño de muestra vienen de config.settings (única fuente de verdad).

Output: data/category_trees/category_keywords.json
Formato:
[
  {
    "url": "https://www.jumbocolombia.com",
    "keywords": ["Electrodomésticos", "Pequeños Electrodomésticos", "Cuidado Personal", ...]
  },
  ...
]
"""

import json

import requests
from loguru import logger

from config import settings


def fetch_tree(store_url: str) -> list[dict]:
    """Trae el árbol crudo de categorías (profundidad 1 = root + hijos directos, sin nietos)."""
    url = f"{store_url}/api/catalog_system/pub/category/tree/1"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DataPipeline/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"[{store_url}] error obteniendo árbol: {e}")
        return []


def extract_keywords(tree: list[dict], children_per_root: int = settings.VTEX_CHILDREN_PER_ROOT) -> list[str]:
    """
    Extrae nombres: cada categoría raíz + sus primeros N hijos directos.
    No baja más profundo que nivel 2.
    """
    keywords: list[str] = []

    for root in tree:
        root_name = root.get("name")
        if root_name:
            keywords.append(root_name)

        children = root.get("children", [])[:children_per_root]
        for child in children:
            child_name = child.get("name")
            if child_name:
                keywords.append(child_name)

    return keywords


def discover_all_stores(stores: list[str] = settings.VTEX_STORES) -> list[dict]:
    """Recorre todas las tiendas y arma la estructura final."""
    result: list[dict] = []

    for store_url in stores:
        logger.info(f"Descubriendo categorías: {store_url}")
        tree = fetch_tree(store_url)

        if not tree:
            logger.warning(f"  → sin árbol, se omite {store_url}")
            continue

        keywords = extract_keywords(tree)
        # Deduplicar manteniendo orden
        keywords = list(dict.fromkeys(keywords))

        result.append({"url": store_url, "keywords": keywords})
        logger.success(f"  → {len(keywords)} keywords extraídas")

    return result


def save(data: list[dict], path=settings.CATEGORY_KEYWORDS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.success(f"Guardado: {path}")


if __name__ == "__main__":
    data = discover_all_stores()
    save(data)

    total_kw = sum(len(s["keywords"]) for s in data)
    logger.info(f"Total: {len(data)} tiendas, {total_kw} keywords combinadas")