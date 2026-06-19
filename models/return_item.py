"""
models/return_item.py
Dataclass tipada para una devolución de producto.

Solo aplica sobre líneas de transactions.parquet con estado_pago=APPROVED
(no se puede devolver lo que nunca se aprobó). Tasa de devolución ~12%,
consistente con benchmarks reales de retail/moda (Baymard/industria:
devoluciones no deberían superar 20%; ~12% es razonable para un mix
de categorías general).
"""

from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class ReturnItem:
    id_devolucion: str
    id_transaccion: str
    id_orden: str
    id_producto: str
    id_usuario: str
    motivo: str               # talla_incorrecta | producto_defectuoso | no_cumple_expectativas | cambio_de_opinion | llego_danado
    estado_devolucion: str     # dinero_devuelto | cambio_producto | credito_tienda
    fecha_solicitud: datetime
    monto_devuelto: float

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "id_devolucion": self.id_devolucion,
            "id_transaccion": self.id_transaccion,
            "id_orden": self.id_orden,
            "id_producto": self.id_producto,
            "id_usuario": self.id_usuario,
            "motivo": self.motivo,
            "estado_devolucion": self.estado_devolucion,
            "fecha_solicitud": self.fecha_solicitud.isoformat(),
            "monto_devuelto": self.monto_devuelto,
        }