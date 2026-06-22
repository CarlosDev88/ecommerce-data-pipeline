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
#   sessions/sessions.parquet                          <- sin particiones (por ahora)
#   transactions/year=*/month=*/day=*/...parquet      <- particionado
#   events/year=*/month=*/day=*/hour=*/events.json    <- particionado
#   datalayer/year=*/month=*/day=*/session_*.json     <- particionado
PATHS = {
    "products":     RAW_STRUCTURED / "products" / "products.parquet",
    "users":        RAW_STRUCTURED / "users",
    "sessions":     RAW_STRUCTURED / "sessions",
    "transactions": RAW_STRUCTURED / "transactions",
    "events":       RAW_SEMI / "events",
    "invoices":     RAW_SEMI / "invoices",
    "fraud_scores": RAW_STRUCTURED / "fraud_scores",
    "datalayer":    RAW_SEMI / "datalayer",
    "processed":    DATA_DIR / "processed",
}

# ─────────────────────────────────────────────
# VTEX API — tiendas colombianas
# Endpoint público: {base_url}/api/catalog_system/pub/products/search
# Sin autenticación requerida
# ─────────────────────────────────────────────

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

VTEX_CHILDREN_PER_ROOT = 5
CATEGORY_TREES_DIR     = DATA_DIR / "category_trees"
CATEGORY_KEYWORDS_PATH = CATEGORY_TREES_DIR / "category_keywords.json"
RAW_EXTRACTION_DIR     = DATA_DIR / "raw_extraction"

VTEX_PAGE_SIZE             = 49   # _from=0&_to=49 = 50 items
VTEX_REQUESTS_PER_SECOND   = 2.0

# ─────────────────────────────────────────────
# SIMULACIÓN — volumen de producción para portfolio
# ─────────────────────────────────────────────
SIM_NUM_USERS    = 50_000
SIM_DATE_START   = "2024-01-01"
SIM_DATE_END     = "2026-05-31"

USER_SEGMENTS: list[dict] = [
    {"segment": "estandar",  "weight": 0.70},
    {"segment": "frecuente", "weight": 0.25},
    {"segment": "VIP",       "weight": 0.05},
]

TRANSACTION_STATUS_RATES: dict[str, float] = {
    "completed":       0.64,
    "fraud":           0.15,
    "technical_error": 0.09,
    "pending":         0.13,
}

TRANSACTION_STATUS_TO_ESTADO_PAGO: dict[str, str] = {
    "completed":       "APPROVED",
    "fraud":           "REJECTED",
    "technical_error": "ERROR",
    "pending":         "PENDING",
}

COLOMBIA_CITIES: list[dict] = [
    {"city": "Bogotá",        "state": "Cundinamarca",        "weight": 0.35},
    {"city": "Medellín",      "state": "Antioquia",           "weight": 0.20},
    {"city": "Cali",          "state": "Valle del Cauca",     "weight": 0.13},
    {"city": "Barranquilla",  "state": "Atlántico",           "weight": 0.08},
    {"city": "Cartagena",     "state": "Bolívar",             "weight": 0.06},
    {"city": "Bucaramanga",   "state": "Santander",           "weight": 0.05},
    {"city": "Pereira",       "state": "Risaralda",           "weight": 0.04},
    {"city": "Manizales",     "state": "Caldas",              "weight": 0.03},
    {"city": "Cúcuta",        "state": "Norte de Santander",  "weight": 0.03},
    {"city": "Ibagué",        "state": "Tolima",              "weight": 0.03},
]

INCOME_SEGMENTS: list[dict] = [
    {"segment": "bajo",       "strata": [1, 2], "weight": 0.45, "avg_order_cop": 80_000},
    {"segment": "medio_bajo", "strata": [3],    "weight": 0.30, "avg_order_cop": 200_000},
    {"segment": "medio_alto", "strata": [4, 5], "weight": 0.18, "avg_order_cop": 500_000},
    {"segment": "alto",       "strata": [6],    "weight": 0.07, "avg_order_cop": 1_500_000},
]

# ─────────────────────────────────────────────
# SESIONES — volumen de producción
# Ratio ~3 sesiones/usuario sobre usuarios activos — realista para
# ventana de 29 meses (ene 2024 – may 2026).
# ─────────────────────────────────────────────
SIM_NUM_SESSIONS          = 150_000
SIM_SESSIONS_ANONIMAS     =  60_000   # 40% — tráfico no autenticado
SIM_SESSIONS_CON_USUARIO  =  90_000   # 60% — pool de 50K usuarios ponderado por segmento

SESSION_PROFILE_WEIGHTS: dict[str, float] = {
    "vitrinero":          0.85,
    "carrito_abandonado": 0.12,
    "intenta_pagar":      0.03,
}

SESSION_CART_VARIATION_RATE    = 0.05
SESSION_EVENT_GAP_SECONDS_MIN  = 15
SESSION_EVENT_GAP_SECONDS_MAX  = 180

CART_SIZE_WEIGHTS = {
    1: 0.22, 2: 0.20, 3: 0.18, 4: 0.14, 5: 0.10,
    6: 0.07, 7: 0.04, 8: 0.03, 9: 0.01, 10: 0.01,
}

# ─────────────────────────────────────────────
# FRAUD — reglas explicativas para órdenes REJECTED
# ─────────────────────────────────────────────
FRAUD_REGLA_PESOS: dict[str, int] = {
    "velocidad_alta":     30,
    "monto_atipico":      25,
    "dispositivo_inusual": 20,
    "ciudad_no_coincide": 15,
    "cvv_mismatch":       35,
}

FRAUD_REGLA_PROBABILIDAD: dict[str, float] = {
    "velocidad_alta":     0.35,
    "monto_atipico":      0.40,
    "dispositivo_inusual": 0.30,
    "ciudad_no_coincide": 0.25,
    "cvv_mismatch":       0.45,
}

FRAUD_SCORE_THRESHOLD_ALTO  = 60
FRAUD_SCORE_THRESHOLD_MEDIO = 30

# ─────────────────────────────────────────────
# STORAGE BACKEND — cambiar aquí para alternar local ↔ GCS
# Valores válidos: "local" | "gcs"
# ─────────────────────────────────────────────
STORAGE_BACKEND = "local"
GCS_BUCKET_NAME = "ecommerce-latam-raw"