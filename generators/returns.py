"""
generators/returns.py
Genera la tabla de devoluciones: ~12% de las líneas de transactions.parquet
con estado_pago=APPROVED se marcan como devueltas, con motivo, resolución
y fecha dentro de una ventana realista de 30 días post-compra.
"""

import random
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

from config import settings
from models.return_item import ReturnItem

RETURN_RATE = 0.12  # ~12%, dentro del rango sano de industria (no debería superar 20%)

MOTIVOS_WEIGHTS = {
    "talla_incorrecta": 0.30,
    "producto_defectuoso": 0.20,
    "no_cumple_expectativas": 0.25,
    "cambio_de_opinion": 0.15,
    "llego_danado": 0.10,
}

ESTADO_DEVOLUCION_WEIGHTS = {
    "dinero_devuelto": 0.55,
    "cambio_producto": 0.30,
    "credito_tienda": 0.15,
}

RETURN_WINDOW_DAYS_MAX = 30


def load_transactions(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/transactions.py")
    return pd.read_parquet(path)


def _weighted_pick(weights_dict: dict[str, float]) -> str:
    return random.choices(list(weights_dict.keys()), weights=list(weights_dict.values()), k=1)[0]


def build_returns(transactions_df: pd.DataFrame) -> pd.DataFrame:
    approved = transactions_df[transactions_df["estado_pago"] == "APPROVED"]
    if approved.empty:
        logger.warning("No hay líneas APPROVED — returns.parquet quedará vacío")
        return pd.DataFrame()

    n_devoluciones = int(round(len(approved) * RETURN_RATE))
    lineas_devueltas = approved.sample(n=min(n_devoluciones, len(approved)), random_state=None)

    rows = []
    for _, line in lineas_devueltas.iterrows():
        fecha_compra = pd.to_datetime(line["fecha_transaccion"])
        dias_despues = random.randint(1, RETURN_WINDOW_DAYS_MAX)
        fecha_solicitud = fecha_compra + timedelta(days=dias_despues)

        item = ReturnItem(
            id_devolucion=ReturnItem.new_id(),
            id_transaccion=line["id_transaccion"],
            id_orden=line["id_orden"],
            id_producto=line["id_producto"],
            id_usuario=line["id_usuario"],
            motivo=_weighted_pick(MOTIVOS_WEIGHTS),
            estado_devolucion=_weighted_pick(ESTADO_DEVOLUCION_WEIGHTS),
            fecha_solicitud=fecha_solicitud,
            monto_devuelto=float(line["monto_linea"]),
        )
        rows.append(item.to_dict())

    return pd.DataFrame(rows)


def run() -> pd.DataFrame:
    transactions_df = load_transactions(settings.PATHS["transactions"] / "transactions.parquet")
    returns_df = build_returns(transactions_df)

    out_dir = settings.PATHS["transactions"].parent / "returns"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "returns.parquet"
    returns_df.to_parquet(out_path, index=False)

    n_approved = (transactions_df["estado_pago"] == "APPROVED").sum()
    logger.success(f"{len(returns_df):,} devoluciones guardadas → {out_path}")
    if n_approved > 0:
        logger.info(f"  tasa real de devolución: {len(returns_df)/n_approved:.1%} (objetivo {RETURN_RATE:.0%})")
    if not returns_df.empty:
        logger.info("── Distribución por motivo ──")
        for motivo, count in returns_df["motivo"].value_counts().items():
            logger.info(f"  {motivo:<24} {count:>4,}")
        logger.info("── Distribución por estado_devolucion ──")
        for est, count in returns_df["estado_devolucion"].value_counts().items():
            logger.info(f"  {est:<18} {count:>4,}")

    return returns_df


if __name__ == "__main__":
    run()