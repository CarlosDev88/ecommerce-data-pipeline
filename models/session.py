"""
models/session.py
Dataclasses tipadas para Session (contenedor) y Event (clickstream/Data Layer).

Regla de login (ver generators/sessions.py para la máquina de estados completa):
  - Sesiones anónimas puras (invitado): id_usuario=None en TODOS sus eventos.
  - Sesiones con usuario destino, segmento VIP/frecuente: id_usuario poblado
    desde view_homepage (sesión de navegador persistente).
  - Sesiones con usuario destino, segmento estandar: id_usuario=None hasta
    add_to_cart (sesión expirada, gate normal de login).
  - Si el perfil conductual de la sesión nunca llega a add_to_cart
    (Vitrinero), id_usuario queda None en el 100% de sus eventos aunque
    tuviera un usuario destino asignado.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Event:
    id_evento: str
    id_sesion: str
    id_usuario: Optional[str]   # None si la sesión aún no está logueada en este punto
    nombre_evento: str          # view_homepage, search_products, view_item_list, view_item,
                                 # select_promotion, add_to_cart, increment_quantity,
                                 # decrement_quantity, remove_from_cart, view_cart,
                                 # begin_checkout, add_shipping_info, add_payment_info, purchase
    timestamp: datetime
    # Payload flexible — cada evento usa un subconjunto distinto de campos,
    # validado contra su schema en pubsub/schemas/{nombre_evento}.json
    payload: dict = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "id_evento": self.id_evento,
            "id_sesion": self.id_sesion,
            "id_usuario": self.id_usuario,
            "nombre_evento": self.nombre_evento,
            "timestamp": self.timestamp.isoformat(),
            **self.payload,
        }


@dataclass
class Session:
    id_sesion: str
    id_usuario_destino: Optional[str]   # usuario "dueño" potencial de la sesión; None si es invitado puro
    es_anonima_pura: bool               # True si nunca puede loguearse (grupo de las 800 invitado)
    perfil: str                         # 'vitrinero' | 'carrito_abandonado' | 'intenta_pagar'
    canal_origen: str
    dispositivo: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    eventos: list[Event] = field(default_factory=list)

    # Resultado de checkout, solo relevante si perfil == 'intenta_pagar'
    transaction_status: Optional[str] = None   # 'completed' | 'fraud' | 'technical_error' | 'pending'
    id_orden: Optional[str] = None
    id_transaccion: Optional[str] = None

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def add_event(self, event: Event) -> None:
        self.eventos.append(event)
        self.fecha_fin = event.timestamp

    def to_session_dict(self) -> dict:
        """Metadata de la sesión (sin los eventos) — fila de la tabla 'sessions'."""
        return {
            "id_sesion": self.id_sesion,
            "id_usuario_destino": self.id_usuario_destino,
            "es_anonima_pura": self.es_anonima_pura,
            "perfil": self.perfil,
            "canal_origen": self.canal_origen,
            "dispositivo": self.dispositivo,
            "fecha_inicio": self.fecha_inicio.isoformat(),
            "fecha_fin": self.fecha_fin.isoformat() if self.fecha_fin else None,
            "n_eventos": len(self.eventos),
            "transaction_status": self.transaction_status,
            "id_orden": self.id_orden,
            "id_transaccion": self.id_transaccion,
        }