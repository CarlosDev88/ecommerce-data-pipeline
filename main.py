"""
main.py
Orquestador del pipeline — ejecuta los generadores en secuencia.
Por ahora solo productos. Los demás generadores se agregan aquí
a medida que se construyen.
"""

from loguru import logger
from storage import get_storage
from generators.products import build_product_generator


def run_products() -> None:
    logger.info("═" * 50)
    logger.info("FASE 1 — Extracción catálogo MercadoLibre Colombia")
    logger.info("═" * 50)

    storage   = get_storage()
    generator = build_product_generator(storage)
    df        = generator.run()

    logger.success(f"Productos extraídos y guardados: {len(df):,}")
    logger.info(f"Categorías: {df['category_name'].value_counts().to_dict()}")


if __name__ == "__main__":
    run_products()