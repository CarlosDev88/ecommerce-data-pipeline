"""
generators/fraud.py
Genera una tabla de score y reglas explicativas para las transacciones
con estado_pago=REJECTED (ya decididas como fraude en transactions.py vía
TRANSACTION_STATUS_RATES). Este módulo NO decide si es fraude — eso ya
pasó — sino que simula qué reglas de un motor antifraude real habrían
disparado la alerta, como tabla de auditoría/explicabilidad.

Reglas, pesos y umbrales centralizados en settings.py
(FRAUD_REGLA_PESOS, FRAUD_REGLA_PROBABILIDAD, FRAUD_SCORE_THRESHOLD_*).
"""

import random

import pandas as pd
from loguru import logger

from config import settings
from models.fraud_score import FraudScore


def load_transactions(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/transactions.py")
    return pd.read_parquet(path)


def load_sessions(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/sessions.py")
    return pd.read_parquet(path)


def _detectar_velocidad_alta(id_usuario: str, sessions_by_user: dict) -> bool:
    """True si el usuario tiene 2+ sesiones que caen dentro de una ventana de 24h."""
    fechas = sessions_by_user.get(id_usuario, [])
    if len(fechas) < 2:
        return False
    fechas_sorted = sorted(fechas)
    for i in range(len(fechas_sorted) - 1):
        if (fechas_sorted[i + 1] - fechas_sorted[i]).total_seconds() < 24 * 3600:
            return True
    return False


def _nivel_confianza(score: int) -> str:
    if score >= settings.FRAUD_SCORE_THRESHOLD_ALTO:
        return "alto"
    if score >= settings.FRAUD_SCORE_THRESHOLD_MEDIO:
        return "medio"
    return "bajo"


def build_fraud_scores(transactions_df: pd.DataFrame, sessions_df: pd.DataFrame) -> pd.DataFrame:
    rejected = transactions_df[transactions_df["estado_pago"] == "REJECTED"].copy()
    if rejected.empty:
        logger.warning("No hay transacciones REJECTED — fraud_scores.parquet quedará vacío")
        return pd.DataFrame()

    # Pre-indexar fechas de sesión por usuario (excluye anónimas, que no tienen id_usuario_destino)
    sessions_with_user = sessions_df[sessions_df["id_usuario_destino"].notna()]
    sessions_by_user: dict[str, list] = {}
    for _, row in sessions_with_user.iterrows():
        sessions_by_user.setdefault(row["id_usuario_destino"], []).append(pd.to_datetime(row["fecha_inicio"]))

    rows = []
    # Una fila por ORDEN (no por línea) — el fraude se evalúa a nivel de orden
    for id_orden, order_lines in rejected.groupby("id_orden"):
        first = order_lines.iloc[0]
        id_usuario = first["id_usuario"]

        reglas_disparadas: list[str] = []
        score = 0

        if _detectar_velocidad_alta(id_usuario, sessions_by_user):
            if random.random() < settings.FRAUD_REGLA_PROBABILIDAD["velocidad_alta"]:
                reglas_disparadas.append("velocidad_alta")
                score += settings.FRAUD_REGLA_PESOS["velocidad_alta"]

        for regla in ["monto_atipico", "dispositivo_inusual", "ciudad_no_coincide", "cvv_mismatch"]:
            if random.random() < settings.FRAUD_REGLA_PROBABILIDAD[regla]:
                reglas_disparadas.append(regla)
                score += settings.FRAUD_REGLA_PESOS[regla]

        # Garantizar que siempre haya al menos una regla explicando el rechazo
        if not reglas_disparadas:
            regla_default = random.choice(list(settings.FRAUD_REGLA_PESOS.keys()))
            reglas_disparadas.append(regla_default)
            score += settings.FRAUD_REGLA_PESOS[regla_default]

        fraud_score = FraudScore(
            id_orden=id_orden,
            id_transaccion=first["id_transaccion"],
            id_usuario=id_usuario,
            score_fraude=score,
            nivel_confianza=_nivel_confianza(score),
            reglas_disparadas=reglas_disparadas,
            monto_total_orden=round(order_lines["monto_linea"].sum(), 2),
            fecha_transaccion=first["fecha_transaccion"],
        )
        rows.append(fraud_score.to_dict())

    return pd.DataFrame(rows)


def run() -> pd.DataFrame:
    transactions_df = load_transactions(settings.PATHS["transactions"] / "transactions.parquet")
    sessions_df = load_sessions(settings.PATHS["sessions"] / "sessions.parquet")

    fraud_df = build_fraud_scores(transactions_df, sessions_df)

    out_dir = settings.PATHS["fraud_scores"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fraud_scores.parquet"
    fraud_df.to_parquet(out_path, index=False)

    logger.success(f"{len(fraud_df):,} órdenes con score de fraude guardadas → {out_path}")
    if not fraud_df.empty:
        logger.info("── Distribución por nivel_confianza ──")
        for nivel, count in fraud_df["nivel_confianza"].value_counts().items():
            logger.info(f"  {nivel:<8} {count:>4,}")
        logger.info(f"  score promedio: {fraud_df['score_fraude'].mean():.1f}")

    return fraud_df


if __name__ == "__main__":
    run()