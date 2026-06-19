"""
generators/transactions.py
Construye transactions.parquet a partir de las sesiones que llegaron a
purchase en events.json. Granularidad: una fila por línea de producto
dentro de la orden (todas las líneas de una misma orden comparten
id_orden / id_transaccion).

Reglas de descuento por promoción (derivadas de cluster_highlights del
producto, texto libre real de VTEX):
  - vacío                          -> sin descuento
  - contiene 'envio'/'envío'/'gratis' -> descuento de envío gratis
    (se anula el envio_prorrateado de esa línea)
  - cualquier otro contenido        -> 10% de descuento sobre el precio
    (no detectamos patrón de % explícito en los datos reales)

metodo_entrega se decide por ORDEN completa (no por línea):
  domicilio 70% / recojo_tienda 30%

costo_envio_calculado (por orden) se prorratea entre líneas proporcional
al peso de cada subtotal_linea sobre el subtotal total de la orden.
Si metodo_entrega = recojo_tienda, el envío es 0 para toda la orden.
"""

import random
import unicodedata

import pandas as pd
from loguru import logger

from config import settings

METODO_ENTREGA_WEIGHTS = {"domicilio": 0.70, "recojo_tienda": 0.30}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _classify_promotion(cluster_highlights) -> str:
    """
    Devuelve 'envio_gratis', '10pct' o 'ninguno' según el contenido de
    cluster_highlights (dict de texto libre real de VTEX).
    """
    if not isinstance(cluster_highlights, dict) or not cluster_highlights:
        return "ninguno"
    texto = " ".join(str(v) for v in cluster_highlights.values())
    texto = _strip_accents(texto.lower())
    if "envio" in texto and "gratis" in texto:
        return "envio_gratis"
    if "gratis" in texto and "envio" in texto:
        return "envio_gratis"
    return "10pct"


def load_events(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/sessions.py")
    df = pd.read_json(path)
    logger.info(f"{len(df):,} eventos cargados")
    return df


def load_products_lookup(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero el pipeline de catálogo")
    df = pd.read_parquet(path, columns=["product_id", "cluster_highlights"])
    return df.set_index("product_id")


def build_transactions(events_df: pd.DataFrame, products_lookup: pd.DataFrame) -> pd.DataFrame:
    purchase_events = events_df[events_df["nombre_evento"] == "purchase"].copy()
    if purchase_events.empty:
        logger.warning("No hay eventos purchase — transactions.parquet quedará vacío")
        return pd.DataFrame()

    rows: list[dict] = []

    for _, purchase in purchase_events.iterrows():
        id_sesion = purchase["id_sesion"]

        # Todos los add_to_cart de la misma sesión = líneas de la orden.
        # (variaciones de cantidad ya quedaron reflejadas en el último
        # add_to_cart/increment/decrement antes de begin_checkout, pero
        # para simplicidad tomamos el snapshot final de cada producto
        # vía el último evento de carrito por id_producto en la sesión)
        session_events = events_df[events_df["id_sesion"] == id_sesion].sort_values("timestamp")
        cart_events = session_events[
            session_events["nombre_evento"].isin(
                ["add_to_cart", "increment_quantity", "decrement_quantity", "remove_from_cart"]
            )
        ]

        cart_state: dict[str, dict] = {}
        for _, ev in cart_events.iterrows():
            pid = ev["id_producto"]
            if ev["nombre_evento"] == "remove_from_cart":
                cart_state.pop(pid, None)
                continue
            cantidad = ev.get("cantidad_nueva")
            if pd.isna(cantidad):
                cantidad = ev.get("cantidad")
            precio_unit = ev.get("precio_unitario")
            cart_state[pid] = {"cantidad": int(cantidad), "precio_unitario": float(precio_unit)}

        # metodo_pago vive en add_payment_info; costo_envio y cupon en begin_checkout
        payment_events = session_events[session_events["nombre_evento"] == "add_payment_info"]
        metodo_pago = payment_events.iloc[-1]["metodo_pago"] if not payment_events.empty else None

        checkout_events = session_events[session_events["nombre_evento"] == "begin_checkout"]
        if not checkout_events.empty:
            costo_envio_orden_raw = checkout_events.iloc[-1]["costo_envio_calculado"]
            cupon = checkout_events.iloc[-1]["cupon_aplicado"]
        else:
            costo_envio_orden_raw = 0.0
            cupon = None

        if not cart_state:
            continue  # caso borde: carrito vacío antes de checkout (ya detectado y aceptado)

        subtotal_orden = sum(v["cantidad"] * v["precio_unitario"] for v in cart_state.values())
        costo_envio_orden = float(costo_envio_orden_raw) if pd.notna(costo_envio_orden_raw) else 0.0
        metodo_entrega = random.choices(
            list(METODO_ENTREGA_WEIGHTS.keys()), weights=list(METODO_ENTREGA_WEIGHTS.values()), k=1
        )[0]
        if metodo_entrega == "recojo_tienda":
            costo_envio_orden = 0.0

        for pid, info in cart_state.items():
            cantidad = info["cantidad"]
            precio_unit = info["precio_unitario"]
            subtotal_linea = cantidad * precio_unit

            peso = (subtotal_linea / subtotal_orden) if subtotal_orden > 0 else 0.0
            envio_prorrateado = round(costo_envio_orden * peso, 2)

            cluster_highlights = (
                products_lookup.loc[pid, "cluster_highlights"] if pid in products_lookup.index else {}
            )
            tipo_descuento = _classify_promotion(cluster_highlights)

            descuento_aplicado = 0.0
            if tipo_descuento == "envio_gratis":
                descuento_aplicado = envio_prorrateado
                envio_prorrateado = 0.0
            elif tipo_descuento == "10pct":
                descuento_aplicado = round(subtotal_linea * 0.10, 2)

            monto_linea = round(subtotal_linea - descuento_aplicado + envio_prorrateado, 2)

            rows.append({
                "id_transaccion": purchase["id_transaccion"],
                "id_orden": purchase["id_orden"],
                "id_sesion": id_sesion,
                "id_usuario": purchase["id_usuario"],
                "id_producto": pid,
                "cantidad": cantidad,
                "precio_unitario": precio_unit,
                "subtotal_linea": round(subtotal_linea, 2),
                "tiene_promocion": tipo_descuento != "ninguno",
                "tipo_descuento": tipo_descuento,
                "descuento_aplicado": descuento_aplicado,
                "envio_prorrateado": envio_prorrateado,
                "monto_linea": monto_linea,
                "metodo_entrega": metodo_entrega,
                "metodo_pago": metodo_pago,
                "estado_pago": purchase["estado_pago"],
                "cupon_aplicado": cupon if pd.notna(cupon) else None,
                "fecha_transaccion": purchase["timestamp"],
            })

    return pd.DataFrame(rows)


def run() -> pd.DataFrame:
    events_df = load_events(settings.PATHS["events"] / "events.json")
    products_lookup = load_products_lookup(settings.PATHS["products"])

    transactions_df = build_transactions(events_df, products_lookup)

    out_dir = settings.PATHS["transactions"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "transactions.parquet"
    transactions_df.to_parquet(out_path, index=False)

    logger.success(f"{len(transactions_df):,} líneas de transacción guardadas → {out_path}")
    if not transactions_df.empty:
        logger.info(f"  órdenes únicas: {transactions_df['id_orden'].nunique():,}")
        logger.info("── Distribución por estado_pago ──")
        for est, count in transactions_df["estado_pago"].value_counts().items():
            logger.info(f"  {est:<12} {count:>5,}")
        logger.info("── Distribución por metodo_entrega ──")
        for met, count in transactions_df["metodo_entrega"].value_counts().items():
            logger.info(f"  {met:<14} {count:>5,} ({count/len(transactions_df):.1%})")
        logger.info("── Distribución por tipo_descuento ──")
        for tipo, count in transactions_df["tipo_descuento"].value_counts().items():
            logger.info(f"  {tipo:<14} {count:>5,}")

    return transactions_df


if __name__ == "__main__":
    run()