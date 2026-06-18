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

# Tiendas VTEX colombianas confirmadas. Única fuente de verdad para
# generators/discover_categories.py y generators/extract_products.py —
# agregar/quitar una tienda es editar solo esta lista.
VTEX_STORES: list[str] = [
    "https://store.sony.com.co",
    "https://www.electrolux.com.co",
    "https://www.whirlpool.com.co",
    "https://www.jumbocolombia.com",
    "https://www.arturocalle.com",
    "https://www.studiof.com.co",
    "https://co.totto.com",
    "https://www.mariohernandez.com.co",
    "https://www.nike.com.co",
    "https://www.asics.com.co",
    "https://www.olimpica.com",
    "https://www.pepeganga.com",
]

# Cuántos hijos directos de cada categoría raíz se toman como keyword
# (discover_categories.py) — muestra reducida para mantener el volumen
# de la prueba manejable.
VTEX_CHILDREN_PER_ROOT = 5

# Paths de la etapa de extracción de catálogo (scripts 1-3)
CATEGORY_TREES_DIR  = DATA_DIR / "category_trees"
CATEGORY_KEYWORDS_PATH = CATEGORY_TREES_DIR / "category_keywords.json"
RAW_EXTRACTION_DIR  = DATA_DIR / "raw_extraction"

# Página de resultados — VTEX permite hasta 50 por request
VTEX_PAGE_SIZE = 49  # _from=0&_to=49 = 50 items

# Rate limiting conservador
VTEX_REQUESTS_PER_SECOND = 2.0

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