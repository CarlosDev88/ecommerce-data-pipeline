"""
generators/sessions.py
Genera 2,000 sesiones de clickstream/Data Layer sobre el pool de usuarios
y el catálogo real de productos.

Estructura (ver decisiones acordadas):
  - 800 sesiones ANÓNIMAS PURAS (invitado): nunca tienen id_usuario, en
    ningún evento. Perfil conductual: Vitrinero forzado.
  - 1,200 sesiones CON USUARIO DESTINO: distribuidas sobre el pool de
    1,000 usuarios, ponderado por segmento (VIP > frecuente > estandar).
    Su perfil conductual se sortea con SESSION_PROFILE_WEIGHTS:
      - vitrinero (85%):          nunca llega a add_to_cart
      - carrito_abandonado (12%): llega a add_to_cart, no llega a pagar
      - intenta_pagar (3%):       llega a add_payment_info; el resultado
                                   (completed/fraud/technical_error/pending)
                                   se decide con TRANSACTION_STATUS_RATES

Regla de login (gate en add_to_cart, salvo sesión persistente):
  - segmento VIP/frecuente  -> id_usuario poblado desde view_homepage
  - segmento estandar       -> id_usuario=None hasta add_to_cart
  - perfil vitrinero        -> nunca se puebla (no llega a add_to_cart)

purchase SIEMPRE se dispara si la sesión llega a add_payment_info, con
estado_pago reflejando el resultado real (APPROVED/REJECTED/PENDING/ERROR),
para mantener trazabilidad 1:1 con transactions.parquet vía id_orden/id_transaccion.
"""

import random
import uuid
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

from config import settings
from models.session import Event, Session

CANALES = ["Google_Ads", "Meta_Ads", "Organic", "Referral", "Email_Marketing", "Influencer", "Direct"]
DISPOSITIVOS = ["Mobile", "Desktop", "Tablet"]
METODOS_ENVIO = ["Envio_Express", "Envio_Normal"]
METODOS_PAGO = ["Tarjeta_Credito", "PSE", "Efectivo"]
CUPONES = [None, None, None, "DESCUENTO10", "DESCUENTO15", "ENVIOGRATIS"]  # ~50% sin cupón
SEARCH_TERMS_FALLBACK = ["tenis running", "smartphone", "sofa sala", "chaqueta jean", "juguete niños"]


def _next_timestamp(current: datetime) -> datetime:
    gap = random.randint(
        settings.SESSION_EVENT_GAP_SECONDS_MIN,
        settings.SESSION_EVENT_GAP_SECONDS_MAX,
    )
    return current + timedelta(seconds=gap)


def _weighted_pick(weights_dict: dict[str, float]) -> str:
    keys = list(weights_dict.keys())
    weights = list(weights_dict.values())
    return random.choices(keys, weights=weights, k=1)[0]


def _make_event(session: Session, nombre: str, ts: datetime, id_usuario: str | None, payload: dict) -> Event:
    return Event(
        id_evento=Event.new_id(),
        id_sesion=session.id_sesion,
        id_usuario=id_usuario,
        nombre_evento=nombre,
        timestamp=ts,
        payload=payload,
    )


def load_users(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/users.py")
    df = pd.read_parquet(path)
    logger.info(f"{len(df):,} usuarios cargados")
    return df


def load_products(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero el pipeline de catálogo")
    df = pd.read_parquet(path, columns=["product_id", "product_name", "brand", "category_path", "price"])
    df = df.dropna(subset=["product_id", "price"])
    logger.info(f"{len(df):,} productos cargados como pool de selección")
    return df


def assign_destination_users(users_df: pd.DataFrame, n_sessions: int) -> list[str]:
    """
    Reparte n_sessions sobre el pool de usuarios, ponderado por segmento:
    VIP sale más veces (4-5 sesiones), frecuente (2-3), estandar (1-2).
    """
    segment_weight = {"VIP": 5.0, "frecuente": 2.5, "estandar": 1.0}
    weights = users_df["segmento"].map(segment_weight).fillna(1.0).tolist()
    ids = users_df["id_usuario"].tolist()
    return random.choices(ids, weights=weights, k=n_sessions)


def pick_product(products_df: pd.DataFrame, preferred_category: str | None) -> pd.Series:
    """Sesga la selección hacia categoria_preferida_vtex del usuario si existe."""
    if preferred_category and random.random() < 0.6:
        subset = products_df[products_df["category_path"] == preferred_category]
        if not subset.empty:
            return subset.sample(1).iloc[0]
    return products_df.sample(1).iloc[0]


def build_session_events(
    session: Session,
    products_df: pd.DataFrame,
    preferred_category: str | None,
    id_usuario_destino: str | None,
    ya_logueado_desde_inicio: bool,
    transaction_status_to_estado_pago: dict,
) -> None:
    """
    Máquina de estados única que cubre los 3 perfiles (vitrinero,
    carrito_abandonado, intenta_pagar). El gate de login se resuelve
    una sola vez en add_to_cart si la sesión no venía ya logueada.
    """
    ts = session.fecha_inicio
    id_usuario_actual = id_usuario_destino if ya_logueado_desde_inicio else None
    ya_logueado = ya_logueado_desde_inicio

    # ── view_homepage ──
    ev = _make_event(session, "view_homepage", ts, id_usuario_actual, {
        "canal_origen": session.canal_origen,
        "dispositivo": session.dispositivo,
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    if session.perfil == "vitrinero":
        ev = _make_event(session, "search_products", ts, id_usuario_actual, {
            "search_term": random.choice(SEARCH_TERMS_FALLBACK),
            "resultados_encontrados": random.randint(1, 50),
        })
        session.add_event(ev)
        ts = _next_timestamp(ts)

        sample = products_df.sample(min(8, len(products_df)))
        ev = _make_event(session, "view_item_list", ts, id_usuario_actual, {
            "categoria_lista": preferred_category or sample.iloc[0]["category_path"],
            "lista_productos_vistos": sample["product_id"].tolist(),
        })
        session.add_event(ev)
        ts = _next_timestamp(ts)

        product = pick_product(products_df, preferred_category)
        ev = _make_event(session, "view_item", ts, id_usuario_actual, {
            "id_producto": product["product_id"],
            "nombre_producto": product["product_name"],
            "precio_actual": float(product["price"]),
            "categoria": product["category_path"],
            "subcategoria": None,
            "brand": product["brand"],
        })
        session.add_event(ev)
        return  # fin de sesión Vitrinero

    # ── carrito_abandonado / intenta_pagar: tramo compartido hasta add_to_cart ──
    product = pick_product(products_df, preferred_category)
    ev = _make_event(session, "view_item", ts, id_usuario_actual, {
        "id_producto": product["product_id"],
        "nombre_producto": product["product_name"],
        "precio_actual": float(product["price"]),
        "categoria": product["category_path"],
        "subcategoria": None,
        "brand": product["brand"],
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    # GATE DE LOGIN: si no se había logueado aún, se puebla aquí
    if not ya_logueado:
        id_usuario_actual = id_usuario_destino
        ya_logueado = True

    n_productos = random.choices(
        list(settings.CART_SIZE_WEIGHTS.keys()),
        weights=list(settings.CART_SIZE_WEIGHTS.values()),
        k=1,
    )[0]

    cart: dict[str, dict] = {}
    cart_total = 0.0
    productos_ya_en_carrito = [product]

    for i in range(n_productos):
        if i == 0:
            prod_actual = product  # el ya visto en view_item
        else:
            prod_actual = pick_product(products_df, preferred_category)
            # evitar duplicar el mismo product_id en la misma orden
            intentos = 0
            while prod_actual["product_id"] in cart and intentos < 5:
                prod_actual = pick_product(products_df, preferred_category)
                intentos += 1

        pid = prod_actual["product_id"]
        if pid in cart:
            continue  # no se logró un producto distinto tras varios intentos, se omite

        cantidad = random.randint(1, 3)
        precio_unit = float(prod_actual["price"])
        cart[pid] = {"cantidad": cantidad, "precio_unitario": precio_unit}
        cart_total += cantidad * precio_unit

        ev = _make_event(session, "add_to_cart", ts, id_usuario_actual, {
            "id_producto": pid,
            "cantidad": cantidad,
            "precio_unitario": precio_unit,
            "valor_carrito_actualizado": round(cart_total, 2),
        })
        session.add_event(ev)
        ts = _next_timestamp(ts)

    # Variación de carrito (~5%): increment / decrement / remove, sobre un producto al azar del carrito
    if random.random() < settings.SESSION_CART_VARIATION_RATE and cart:
        variation = random.choice(["increment", "decrement", "remove"])
        pid = random.choice(list(cart.keys()))
        precio_unit = cart[pid]["precio_unitario"]
        if variation == "increment":
            anterior = cart[pid]["cantidad"]
            cart[pid]["cantidad"] += 1
            cart_total += precio_unit
            ev = _make_event(session, "increment_quantity", ts, id_usuario_actual, {
                "id_producto": pid,
                "cantidad_anterior": anterior,
                "cantidad_nueva": cart[pid]["cantidad"],
                "precio_unitario": precio_unit,
                "valor_carrito_actualizado": round(cart_total, 2),
            })
            session.add_event(ev)
            ts = _next_timestamp(ts)
        elif variation == "decrement" and cart[pid]["cantidad"] > 1:
            anterior = cart[pid]["cantidad"]
            cart[pid]["cantidad"] -= 1
            cart_total -= precio_unit
            ev = _make_event(session, "decrement_quantity", ts, id_usuario_actual, {
                "id_producto": pid,
                "cantidad_anterior": anterior,
                "cantidad_nueva": cart[pid]["cantidad"],
                "precio_unitario": precio_unit,
                "valor_carrito_actualizado": round(cart_total, 2),
            })
            session.add_event(ev)
            ts = _next_timestamp(ts)
        elif variation == "remove":
            cart_total -= cart[pid]["cantidad"] * precio_unit
            del cart[pid]
            ev = _make_event(session, "remove_from_cart", ts, id_usuario_actual, {
                "id_producto": pid,
                "valor_carrito_actualizado": round(max(cart_total, 0.0), 2),
            })
            session.add_event(ev)
            ts = _next_timestamp(ts)

    if not cart:
        return  # el carrito quedó vacío por el remove — fin de sesión

    ev = _make_event(session, "view_cart", ts, id_usuario_actual, {
        "productos_en_carrito": list(cart.keys()),
        "monto_acumulado": round(cart_total, 2),
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    costo_envio = round(random.uniform(8_000, 25_000), 0)
    cupon = random.choice(CUPONES)
    ev = _make_event(session, "begin_checkout", ts, id_usuario_actual, {
        "monto_subtotal": round(cart_total, 2),
        "costo_envio_calculado": costo_envio,
        "cupon_aplicado": cupon,
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    if session.perfil == "carrito_abandonado":
        return  # abandono justo después de begin_checkout

    # ── intenta_pagar: flujo completo hasta purchase ──
    ev = _make_event(session, "add_shipping_info", ts, id_usuario_actual, {
        "metodo_envio": random.choice(METODOS_ENVIO),
        "ciudad_destino": random.choice([c["city"] for c in settings.COLOMBIA_CITIES]),
        "tiempo_entrega_estimado": random.choice(["1-2 dias", "2-3 dias", "3-5 dias"]),
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    ev = _make_event(session, "add_payment_info", ts, id_usuario_actual, {
        "metodo_pago": random.choice(METODOS_PAGO),
    })
    session.add_event(ev)
    ts = _next_timestamp(ts)

    estado_pago = transaction_status_to_estado_pago[session.transaction_status]
    descuento = 0.0
    if cupon == "DESCUENTO10":
        descuento = cart_total * 0.10
    elif cupon == "DESCUENTO15":
        descuento = cart_total * 0.15
    monto_total = round(cart_total - descuento + costo_envio, 2)
    impuestos = round(monto_total * 0.19 / 1.19, 2)  # IVA Colombia incluido en el precio

    session.id_orden = str(uuid.uuid4())
    session.id_transaccion = str(uuid.uuid4())

    ev = _make_event(session, "purchase", ts, id_usuario_actual, {
        "id_orden": session.id_orden,
        "id_transaccion": session.id_transaccion,
        "monto_total": monto_total,
        "impuestos": impuestos,
        "estado_pago": estado_pago,
    })
    session.add_event(ev)


def run(n_sessions: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_sessions = n_sessions or settings.SIM_NUM_SESSIONS
    n_anon = settings.SIM_SESSIONS_ANONIMAS
    n_con_usuario = settings.SIM_SESSIONS_CON_USUARIO

    users_df = load_users(settings.PATHS["users"] / "users.parquet")
    products_df = load_products(settings.PATHS["products"])

    users_by_id = users_df.set_index("id_usuario")
    destino_ids = assign_destination_users(users_df, n_con_usuario)

    sim_start = pd.Timestamp(settings.SIM_DATE_START)
    sim_end = pd.Timestamp(settings.SIM_DATE_END)

    sessions: list[Session] = []

    # ── 800 anónimas puras: nunca tienen destino, siempre Vitrinero ──
    for _ in range(n_anon):
        fecha_inicio = (sim_start + (sim_end - sim_start) * random.random()).to_pydatetime()
        session = Session(
            id_sesion=Session.new_id(),
            id_usuario_destino=None,
            es_anonima_pura=True,
            perfil="vitrinero",
            canal_origen=random.choice(CANALES),
            dispositivo=random.choice(DISPOSITIVOS),
            fecha_inicio=fecha_inicio,
        )
        build_session_events(
            session, products_df, preferred_category=None,
            id_usuario_destino=None, ya_logueado_desde_inicio=False,
            transaction_status_to_estado_pago=settings.TRANSACTION_STATUS_TO_ESTADO_PAGO,
        )
        sessions.append(session)

    # ── 1,200 con usuario destino ──
    for uid in destino_ids:
        user_row = users_by_id.loc[uid]
        segmento = user_row["segmento"]
        preferred_category = user_row.get("categoria_preferida_vtex")

        perfil = _weighted_pick(settings.SESSION_PROFILE_WEIGHTS)
        fecha_inicio = (sim_start + (sim_end - sim_start) * random.random()).to_pydatetime()

        session = Session(
            id_sesion=Session.new_id(),
            id_usuario_destino=uid,
            es_anonima_pura=False,
            perfil=perfil,
            canal_origen=random.choice(CANALES),
            dispositivo=random.choice(DISPOSITIVOS),
            fecha_inicio=fecha_inicio,
        )

        if perfil == "intenta_pagar":
            session.transaction_status = _weighted_pick(settings.TRANSACTION_STATUS_RATES)

        # Sesión persistente: VIP/frecuente arrancan logueados desde view_homepage
        ya_logueado_desde_inicio = segmento in ("VIP", "frecuente")

        build_session_events(
            session, products_df, preferred_category=preferred_category,
            id_usuario_destino=uid, ya_logueado_desde_inicio=ya_logueado_desde_inicio,
            transaction_status_to_estado_pago=settings.TRANSACTION_STATUS_TO_ESTADO_PAGO,
        )
        sessions.append(session)

    random.shuffle(sessions)

    sessions_df = pd.DataFrame([s.to_session_dict() for s in sessions])

    all_events = []
    for s in sessions:
        for e in s.eventos:
            all_events.append(e.to_dict())
    events_df = pd.DataFrame(all_events)

    out_dir_sessions = settings.PATHS["users"].parent / "sessions"
    out_dir_sessions.mkdir(parents=True, exist_ok=True)
    sessions_path = out_dir_sessions / "sessions.parquet"
    sessions_df.to_parquet(sessions_path, index=False)

    out_dir_events = settings.PATHS["events"]
    out_dir_events.mkdir(parents=True, exist_ok=True)
    events_path = out_dir_events / "events.json"
    events_df.to_json(events_path, orient="records", date_format="iso", force_ascii=False)

    logger.success(f"{len(sessions_df):,} sesiones guardadas → {sessions_path}")
    logger.success(f"{len(events_df):,} eventos guardados → {events_path}")
    logger.info("── Distribución por perfil ──")
    for perfil, count in sessions_df["perfil"].value_counts().items():
        logger.info(f"  {perfil:<20} {count:>5,} ({count/len(sessions_df):.1%})")
    logger.info("── Sesiones con id_usuario_destino vs anónimas puras ──")
    logger.info(f"  con destino   {(~sessions_df['es_anonima_pura']).sum():>5,}")
    logger.info(f"  anonima_pura  {sessions_df['es_anonima_pura'].sum():>5,}")
    logger.info("── transaction_status (solo perfil intenta_pagar) ──")
    tx = sessions_df[sessions_df["transaction_status"].notna()]
    if not tx.empty:
        for status, count in tx["transaction_status"].value_counts().items():
            logger.info(f"  {status:<18} {count:>5,}")

    return sessions_df, events_df


if __name__ == "__main__":
    run()