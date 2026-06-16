"""
config/settings.py
Parámetros globales del pipeline. Cambiar categorías, límites o paths aquí
no requiere tocar ningún otro archivo.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carga .env desde la raíz del proyecto — no hace nada si no existe
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ─────────────────────────────────────────────
# CREDENCIALES GCP — leídas del .env
# ─────────────────────────────────────────────
GCP_PROJECT_ID  = os.getenv("GCP_PROJECT_ID", "")
GCP_KEY_PATH    = os.getenv("GCP_KEY_PATH", "")

# ML credentials — guardadas para referencia, ya no se usan en extracción
ML_APP_ID        = os.getenv("ML_APP_ID", "")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "")
ML_ACCESS_TOKEN  = os.getenv("ML_ACCESS_TOKEN", "")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN", "")

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

RAW_STRUCTURED = DATA_DIR / "raw" / "structured"
RAW_SEMI       = DATA_DIR / "raw" / "semi-structured"

# Estructura del data lake:
#   products/products.parquet                         <- sin particiones
#   users/year=*/month=*/users.parquet                <- particionado
#   transactions/year=*/month=*/day=*/...parquet      <- particionado
#   events/year=*/month=*/day=*/hour=*/events.json    <- particionado
#   datalayer/year=*/month=*/day=*/session_*.json     <- particionado
PATHS = {
    "products":     RAW_STRUCTURED / "products" / "products.parquet",
    "users":        RAW_STRUCTURED / "users",
    "transactions": RAW_STRUCTURED / "transactions",
    "events":       RAW_SEMI / "events",
    "datalayer":    RAW_SEMI / "datalayer",
    "processed":    DATA_DIR / "processed",
}

# ─────────────────────────────────────────────
# VTEX API — tiendas colombianas
# Endpoint público: {base_url}/api/catalog_system/pub/products/search
# Sin autenticación requerida
# ─────────────────────────────────────────────

# Página de resultados — VTEX permite hasta 50 por request
VTEX_PAGE_SIZE = 49  # _from=0&_to=49 = 50 items

# Rate limiting conservador
VTEX_REQUESTS_PER_SECOND = 2.0

# ─────────────────────────────────────────────
# CATEGORÍAS Y TIENDAS — CONFIGURABLE
# Estructura:
#   categoria_name:
#     target: productos objetivo
#     sources: lista de tiendas con sus keywords de búsqueda
#
# Para agregar/quitar una categoría o tienda: editar solo este dict.
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# VTEX CATEGORIES — Multi-tienda colombiana con category IDs reales
#
# Cada categoría tiene múltiples fuentes con sus cat_ids reales
# obtenidos de /api/catalog_system/pub/category/tree/2
#
# Estrategia: fq=C:{id} trae TODO el catálogo de esa categoría
# Cambiar fuentes: editar solo este dict
# ─────────────────────────────────────────────────────────────────
VTEX_CATEGORIES: dict[str, dict] = {

    "Electrónica y Tecnología": {
        "target": 1200,
        "sources": [
            # Jumbo — Tecnología + TV y Audio + Celulares
            {"store": "https://www.jumbocolombia.com", "category_ids": [47, 2000666, 2000841]},
            # Sony Colombia — Cámaras(1) + Celulares(4) + TV(8) + Gaming(14)
            {"store": "https://store.sony.com.co",     "category_ids": [1, 4, 8, 14]},
            # Electrolux — Limpieza(1) + Lavado(2) + Refrigeración + Cocina
            {"store": "https://www.electrolux.com.co", "category_ids": [1, 2]},
            # Whirlpool — Lavadoras(1) + Neveras(9) + Cocina
            {"store": "https://www.whirlpool.com.co",  "category_ids": [1, 9]},
        ],
    },

    "Ropa y Moda": {
        "target": 1200,
        "sources": [
            # Arturo Calle — Hombre(205) + Mujer si existe
            {"store": "https://www.arturocalle.com",       "category_ids": [205]},
            # Studio F — Ropa(1) completo
            {"store": "https://www.studiof.com.co",        "category_ids": [1]},
            # Totto — Hombre(1) + Mujer(2) + Niños
            {"store": "https://co.totto.com",              "category_ids": [1, 2]},
            # Mario Hernandez — Hombre(1) + Mujer(2)
            {"store": "https://www.mariohernandez.com.co", "category_ids": [1, 2]},
            # Jumbo — Ropa y Accesorios completo
            {"store": "https://www.jumbocolombia.com",     "category_ids": [2000350]},
        ],
    },

    "Hogar y Muebles": {
        "target": 1000,
        "sources": [
            # Jumbo — Hogar y Decoración completo
            {"store": "https://www.jumbocolombia.com",     "category_ids": [1000030]},
            # Electrolux — línea hogar
            {"store": "https://www.electrolux.com.co",     "category_ids": [1, 2]},
            # Whirlpool — electrodomésticos hogar
            {"store": "https://www.whirlpool.com.co",      "category_ids": [1, 9]},
        ],
    },

    "Deportes y Fitness": {
        "target": 1000,
        "sources": [
            # Nike Colombia — Hombre(1) + Mujer(18)
            {"store": "https://www.nike.com.co",   "category_ids": [1, 18]},
            # Asics — Unisex(68) + Kids(3)
            {"store": "https://www.asics.com.co",  "category_ids": [68, 3, 75]},
            # Jumbo — Deportes y Tiempo Libre completo
            {"store": "https://www.jumbocolombia.com", "category_ids": [116]},
            # Olímpica — Deportes
            {"store": "https://www.olimpica.com",  "category_ids": [13000000]},
        ],
    },

    "Belleza y Cuidado": {
        "target": 800,
        "sources": [
            # Jumbo — Cuidado Personal(2000014) + Belleza(2000020)
            {"store": "https://www.jumbocolombia.com", "category_ids": [2000014, 2000020]},
            # Olímpica — Belleza y Cuidado
            {"store": "https://www.olimpica.com",      "category_ids": [6000000]},
        ],
    },

    "Juegos y Juguetes": {
        "target": 800,
        "sources": [
            # Pepe Ganga — Juguetería(1) completa — especialista #1 Colombia
            {"store": "https://www.pepeganga.com",     "category_ids": [1]},
            # Jumbo — Juguetería completa
            {"store": "https://www.jumbocolombia.com", "category_ids": [1000037]},
            # Olímpica — Juguetería(11000000)
            {"store": "https://www.olimpica.com",      "category_ids": [11000000]},
        ],
    },
}

# ─────────────────────────────────────────────
# SIMULACIÓN — parámetros del pipeline sintético
# ─────────────────────────────────────────────
SIM_NUM_USERS = 50_000
SIM_DATE_START = "2024-01-01"
SIM_DATE_END   = "2024-12-31"

# Funnel de conversión — debe sumar 1.0
TRANSACTION_STATUS_RATES: dict[str, float] = {
    "completed":       0.35,
    "abandoned":       0.45,
    "fraud":           0.08,
    "technical_error": 0.05,
    "pending":         0.07,
}

# Distribución geográfica colombiana (ciudades principales)
COLOMBIA_CITIES: list[dict] = [
    {"city": "Bogotá",        "state": "Cundinamarca",    "weight": 0.35},
    {"city": "Medellín",      "state": "Antioquia",       "weight": 0.20},
    {"city": "Cali",          "state": "Valle del Cauca", "weight": 0.13},
    {"city": "Barranquilla",  "state": "Atlántico",       "weight": 0.08},
    {"city": "Cartagena",     "state": "Bolívar",         "weight": 0.06},
    {"city": "Bucaramanga",   "state": "Santander",       "weight": 0.05},
    {"city": "Pereira",       "state": "Risaralda",       "weight": 0.04},
    {"city": "Manizales",     "state": "Caldas",          "weight": 0.03},
    {"city": "Cúcuta",        "state": "Norte de Santander", "weight": 0.03},
    {"city": "Ibagué",        "state": "Tolima",          "weight": 0.03},
]

# Segmentación de poder adquisitivo (estratos Colombia)
INCOME_SEGMENTS: list[dict] = [
    {"segment": "bajo",        "strata": [1, 2], "weight": 0.45, "avg_order_cop": 80_000},
    {"segment": "medio_bajo",  "strata": [3],    "weight": 0.30, "avg_order_cop": 200_000},
    {"segment": "medio_alto",  "strata": [4, 5], "weight": 0.18, "avg_order_cop": 500_000},
    {"segment": "alto",        "strata": [6],    "weight": 0.07, "avg_order_cop": 1_500_000},
]

# ─────────────────────────────────────────────
# STORAGE BACKEND — cambiar aquí para alternar local ↔ GCS
# Valores válidos: "local" | "gcs"
# ─────────────────────────────────────────────
STORAGE_BACKEND = "local"
GCS_BUCKET_NAME = "ecommerce-latam-raw"  # usado solo si STORAGE_BACKEND = "gcs"