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
"""

import random
from datetime import date, datetime, timedelta

import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker
from loguru import logger

from config import settings
from models.user import User

fake = Faker("es_CO")

INACTIVITY_THRESHOLD_MONTHS = 6

ESTADO_CUENTA_WEIGHTS = {"activo": 0.85, "suspendido": 0.03}  # 'inactivo' se calcula, no se sortea
CANAL_ADQUISICION = ["Google_Ads", "Meta_Ads", "Organic", "Referral", "Email_Marketing", "Influencer"]
DISPOSITIVO_REGISTRO = ["Mobile", "Desktop", "Tablet"]
GENEROS = ["femenino", "masculino", "no_binario", "prefiere_no_decir"]
GENEROS_WEIGHTS = [0.47, 0.47, 0.03, 0.03]

TIPO_DOCUMENTO_WEIGHTS = {"cedula": 0.92, "NIT": 0.05, "cedula_extranjeria": 0.03}


def _generate_documento(tipo: str) -> str:
    if tipo == "cedula":
        return str(random.randint(1_000_000_000, 1_199_999_999))  # 10 digitos, rango realista CO
    if tipo == "NIT":
        base = random.randint(800_000_000, 900_000_000)
        dv = random.randint(0, 9)
        return f"{base}-{dv}"
    return f"CE{random.randint(1_000_000, 9_999_999)}"  # cedula_extranjeria


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_category_pool(path) -> list[str]:
    """Carga category_path únicos reales desde products.parquet."""
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero el pipeline de catálogo")
    df = pd.read_parquet(path, columns=["category_path"])
    pool = df["category_path"].dropna().unique().tolist()
    if not pool:
        raise ValueError("products.parquet no tiene category_path válidos")
    logger.info(f"{len(pool)} category_path únicos cargados como pool de preferencia")
    return pool


def _weighted_choice(options: list[dict], key: str) -> str:
    values = [o[key] for o in options]
    weights = [o["weight"] for o in options]
    return random.choices(values, weights=weights, k=1)[0]


def _random_datetime_between(start: date, end: date) -> datetime:
    """Uniforme — usado para fecha_registro (no hay razón para sesgarla)."""
    delta_days = (end - start).days
    offset = random.randint(0, max(delta_days, 0))
    rand_seconds = random.randint(0, 86_399)
    return datetime.combine(start, datetime.min.time()) + timedelta(days=offset, seconds=rand_seconds)


def _recent_biased_datetime_between(start: date, end: date, alpha: float = 4.0, beta: float = 1.0) -> datetime:
    """
    Sesgada hacia 'end' usando distribución Beta(alpha, beta).
    Con alpha=4, beta=1 la mayoría de valores cae en el último tercio
    del rango — modela que la mayoría de usuarios tuvo actividad
    reciente, con una cola hacia atrás para los que se alejaron.
    Usado para fecha_ultima_actividad (no uniforme: uniforme da una
    tasa de inactividad artificialmente alta, ~48%).
    """
    delta_days = (end - start).days
    if delta_days <= 0:
        return datetime.combine(start, datetime.min.time())
    fraction = random.betavariate(alpha, beta)
    offset = int(fraction * delta_days)
    rand_seconds = random.randint(0, 86_399)
    return datetime.combine(start, datetime.min.time()) + timedelta(days=offset, seconds=rand_seconds)


def _build_estado_cuenta(fecha_ultima_actividad: datetime, sim_end: date) -> str:
    inactivity_cutoff = sim_end - relativedelta(months=INACTIVITY_THRESHOLD_MONTHS)
    if fecha_ultima_actividad.date() < inactivity_cutoff:
        return "inactivo"
    return random.choices(
        list(ESTADO_CUENTA_WEIGHTS.keys()),
        weights=list(ESTADO_CUENTA_WEIGHTS.values()),
        k=1,
    )[0]


def generate_user(category_pool: list[str], sim_start: date, sim_end: date) -> User:
    genero = random.choices(GENEROS, weights=GENEROS_WEIGHTS, k=1)[0]

    fecha_registro = _random_datetime_between(sim_start, sim_end)
    # actividad nunca antes del registro ni después de SIM_DATE_END
    # sesgada a fechas recientes (Beta) — uniforme da inactividad artificialmente alta
    fecha_ultima_actividad = _recent_biased_datetime_between(fecha_registro.date(), sim_end)

    fecha_nacimiento = fake.date_of_birth(minimum_age=18, maximum_age=75)

    segmento = _weighted_choice(settings.USER_SEGMENTS, "segment")

    estado_cuenta = _build_estado_cuenta(fecha_ultima_actividad, sim_end)

    city_info = _weighted_choice(settings.COLOMBIA_CITIES, "city")
    # _weighted_choice devuelve el valor de 'city', pero necesitamos el dict completo para 'state' si se requiere
    city_dict = next(c for c in settings.COLOMBIA_CITIES if c["city"] == city_info)

    tipo_documento = random.choices(
        list(TIPO_DOCUMENTO_WEIGHTS.keys()),
        weights=list(TIPO_DOCUMENTO_WEIGHTS.values()),
        k=1,
    )[0]
    numero_documento = _generate_documento(tipo_documento)

    return User(
        id_usuario=User.new_id(),
        nombre_completo=fake.name(),
        correo_electronico=fake.unique.email(),
        telefono_movil=fake.phone_number(),
        fecha_registro=fecha_registro,
        fecha_nacimiento=fecha_nacimiento,
        genero=genero,
        ciudad=city_dict["city"],
        pais="Colombia",
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        estado_cuenta=estado_cuenta,
        verificado_email=random.random() < 0.80,
        verificado_sms=random.random() < 0.55,
        acepta_habeas_data=True,  # obligatorio legal en Colombia para registrarse
        acepta_marketing_email=random.random() < 0.60,
        canal_adquisicion=random.choice(CANAL_ADQUISICION),
        dispositivo_registro=random.choice(DISPOSITIVO_REGISTRO),
        segmento=segmento,
        categoria_preferida_vtex=random.choice(category_pool),
        fecha_ultima_actividad=fecha_ultima_actividad,
    )


def run(n_users: int | None = None) -> pd.DataFrame:
    n_users = n_users or settings.SIM_NUM_USERS
    sim_start = _parse_date(settings.SIM_DATE_START)
    sim_end = _parse_date(settings.SIM_DATE_END)

    category_pool = load_category_pool(settings.PATHS["products"])

    fake.unique.clear()
    users = [generate_user(category_pool, sim_start, sim_end) for _ in range(n_users)]

    df = pd.DataFrame([u.to_dict() for u in users])

    out_dir = settings.PATHS["users"]
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