"""
generators/users.py
Genera usuarios sintéticos colombianos con Faker, sesgados por segmento
de comportamiento (USER_SEGMENTS) y nivel de ingreso (INCOME_SEGMENTS).

categoria_preferida_vtex se samplea de las category_path REALES que
existen en products.parquet — no se inventa, para que sessions.py y
transactions.py puedan usarla para sesgar selección de productos
sobre el catálogo real.

estado_cuenta='inactivo' si fecha_ultima_actividad cae más de 6 meses
antes de SIM_DATE_END (referencia fija del dataset, no la fecha real
de ejecución del script).

Optimización de rendimiento (50K+ usuarios):
- Campos sin restricción de unicidad se generan en bloque con numpy
- Faker solo se usa para nombre_completo, telefono_movil y fecha_nacimiento
- correo_electronico se construye con UUID para evitar el set interno
  de fake.unique que se vuelve O(n²) conforme crece
"""

import uuid
import random
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker
from loguru import logger

from config import settings
from models.user import User

fake = Faker("es_CO")

INACTIVITY_THRESHOLD_MONTHS = 6

ESTADO_CUENTA_WEIGHTS = {"activo": 0.85, "suspendido": 0.03}
CANAL_ADQUISICION    = ["Google_Ads", "Meta_Ads", "Organic", "Referral", "Email_Marketing", "Influencer"]
DISPOSITIVO_REGISTRO = ["Mobile", "Desktop", "Tablet"]
GENEROS         = ["femenino", "masculino", "no_binario", "prefiere_no_decir"]
GENEROS_WEIGHTS = [0.47, 0.47, 0.03, 0.03]

TIPO_DOCUMENTO_WEIGHTS = {"cedula": 0.92, "NIT": 0.05, "cedula_extranjeria": 0.03}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _generate_documento(tipo: str) -> str:
    if tipo == "cedula":
        return str(random.randint(1_000_000_000, 1_199_999_999))
    if tipo == "NIT":
        base = random.randint(800_000_000, 900_000_000)
        dv   = random.randint(0, 9)
        return f"{base}-{dv}"
    return f"CE{random.randint(1_000_000, 9_999_999)}"


def load_category_pool(path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero el pipeline de catálogo")
    df   = pd.read_parquet(path, columns=["category_path"])
    pool = df["category_path"].dropna().unique().tolist()
    if not pool:
        raise ValueError("products.parquet no tiene category_path válidos")
    logger.info(f"{len(pool)} category_path únicos cargados como pool de preferencia")
    return pool


# ─────────────────────────────────────────────
# Generación vectorizada por columna
# ─────────────────────────────────────────────

def _vec_dates_uniform(start: date, end: date, n: int) -> np.ndarray:
    """n fechas uniformes entre start y end como timestamps numpy."""
    delta = (end - start).days
    offsets = np.random.randint(0, max(delta, 1), size=n)
    seconds = np.random.randint(0, 86_400, size=n)
    base = np.datetime64(start, "s")
    return base + offsets.astype("timedelta64[D]") + seconds.astype("timedelta64[s]")


def _vec_dates_beta(start_dates: np.ndarray, end: date, n: int,
                    alpha: float = 4.0, beta: float = 1.0) -> np.ndarray:
    """
    n fechas con distribución Beta(alpha, beta) entre start_dates[i] y end.
    start_dates es array de np.datetime64[s] (fecha_registro por usuario).
    Con alpha=4, beta=1 la mayoría cae en el último tercio del rango.
    """
    end_ns  = np.datetime64(end, "s")
    deltas  = (end_ns - start_dates).astype("timedelta64[s]").astype(np.int64)
    deltas  = np.maximum(deltas, 0)
    fracs   = np.random.beta(alpha, beta, size=n)
    offsets = (fracs * deltas).astype(np.int64)
    seconds = np.random.randint(0, 86_400, size=n)
    return start_dates + offsets.astype("timedelta64[s]") + seconds.astype("timedelta64[s]")


def _vec_estado_cuenta(fecha_ultima_actividad: np.ndarray, sim_end: date, n: int) -> np.ndarray:
    """
    Vectoriza la regla de inactividad:
      - si fecha_ultima_actividad < (sim_end - 6 meses) → 'inactivo'
      - si no → 'activo'(85%) o 'suspendido'(3%), resto 'activo'
    """
    cutoff = np.datetime64(sim_end - relativedelta(months=INACTIVITY_THRESHOLD_MONTHS), "s")
    is_inactive = fecha_ultima_actividad < cutoff

    # para los activos: 85% activo, 3% suspendido, 12% activo también
    # (suspendido es 3% del total de no-inactivos)
    rand     = np.random.random(n)
    estados  = np.where(is_inactive, "inactivo",
               np.where(rand < 0.03, "suspendido", "activo"))
    return estados


def _vec_weighted_choice(options: list[dict], key: str, weight_key: str, n: int) -> np.ndarray:
    values  = [o[key]        for o in options]
    weights = [o[weight_key] for o in options]
    return np.random.choice(values, size=n, p=np.array(weights) / sum(weights))


# ─────────────────────────────────────────────
# run()
# ─────────────────────────────────────────────

def run(n_users: int | None = None) -> pd.DataFrame:
    n        = n_users or settings.SIM_NUM_USERS
    sim_start = _parse_date(settings.SIM_DATE_START)
    sim_end   = _parse_date(settings.SIM_DATE_END)

    category_pool = load_category_pool(settings.PATHS["products"])

    logger.info(f"Generando {n:,} usuarios (vectorizado)…")

    # ── Columnas vectorizadas ──────────────────────────────────────────
    ids            = [str(uuid.uuid4()) for _ in range(n)]
    fecha_registro = _vec_dates_uniform(sim_start, sim_end, n)
    fecha_ult_act  = _vec_dates_beta(fecha_registro, sim_end, n)
    estado_cuenta  = _vec_estado_cuenta(fecha_ult_act, sim_end, n)

    segmentos      = _vec_weighted_choice(settings.USER_SEGMENTS, "segment", "weight", n)
    cities_idx     = _vec_weighted_choice(settings.COLOMBIA_CITIES, "city", "weight", n)
    states         = np.array([
        next(c["state"] for c in settings.COLOMBIA_CITIES if c["city"] == city)
        for city in cities_idx
    ])

    tipos_doc      = np.random.choice(
        list(TIPO_DOCUMENTO_WEIGHTS.keys()),
        size=n,
        p=np.array(list(TIPO_DOCUMENTO_WEIGHTS.values()))
    )
    numeros_doc    = [_generate_documento(t) for t in tipos_doc]

    generos        = np.random.choice(GENEROS, size=n, p=GENEROS_WEIGHTS)
    canales        = np.random.choice(CANAL_ADQUISICION, size=n)
    dispositivos   = np.random.choice(DISPOSITIVO_REGISTRO, size=n)
    categorias     = np.random.choice(category_pool, size=n)

    verificado_email   = np.random.random(n) < 0.80
    verificado_sms     = np.random.random(n) < 0.55
    acepta_marketing   = np.random.random(n) < 0.60

    # ── Campos que requieren Faker (no vectorizables sin perder calidad) ─
    logger.info("  Generando nombres y teléfonos con Faker…")
    nombres   = [fake.name()         for _ in range(n)]
    telefonos = [fake.phone_number() for _ in range(n)]

    # Fecha de nacimiento: Faker internamente ya es razonablemente rápido
    # para esto, pero lo hacemos en bloque igual
    fechas_nac = [fake.date_of_birth(minimum_age=18, maximum_age=75) for _ in range(n)]

    # Correo: UUID en lugar de fake.unique.email() — evita el set interno
    # de Faker que se vuelve O(n²) a partir de ~10K registros.
    # Formato: {slug_nombre}_{uuid8}@{dominio}
    dominios = ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]
    correos  = [
        f"{nombre.split()[0].lower()}.{str(uuid.uuid4())[:8]}@{random.choice(dominios)}"
        for nombre in nombres
    ]

    # ── Ensamblar DataFrame directamente (sin instanciar User) ───────────
    df = pd.DataFrame({
        "id_usuario":               ids,
        "nombre_completo":          nombres,
        "correo_electronico":       correos,
        "telefono_movil":           telefonos,
        "fecha_registro":           pd.to_datetime(fecha_registro),
        "fecha_nacimiento":         fechas_nac,
        "genero":                   generos,
        "ciudad":                   cities_idx,
        "departamento":             states,
        "pais":                     "Colombia",
        "tipo_documento":           tipos_doc,
        "numero_documento":         numeros_doc,
        "estado_cuenta":            estado_cuenta,
        "verificado_email":         verificado_email,
        "verificado_sms":           verificado_sms,
        "acepta_habeas_data":       True,
        "acepta_marketing_email":   acepta_marketing,
        "canal_adquisicion":        canales,
        "dispositivo_registro":     dispositivos,
        "segmento":                 segmentos,
        "categoria_preferida_vtex": categorias,
        "fecha_ultima_actividad":   pd.to_datetime(fecha_ult_act),
    })

    out_dir  = settings.PATHS["users"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "users.parquet"
    df.to_parquet(out_path, index=False)

    logger.success(f"{len(df):,} usuarios generados → {out_path}")
    logger.info("── Distribución por segmento ──")
    for seg, count in df["segmento"].value_counts().items():
        logger.info(f"  {seg:<12} {count:>5,} ({count/len(df):.1%})")
    logger.info("── Distribución por estado_cuenta ──")
    for est, count in df["estado_cuenta"].value_counts().items():
        logger.info(f"  {est:<12} {count:>5,} ({count/len(df):.1%})")

    return df


if __name__ == "__main__":
    run()