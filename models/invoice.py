"""
models/invoice.py
Dataclasses tipadas para Invoice (factura) e InvoiceItem (línea de detalle).

A diferencia de Session/Event, una Invoice no se construye incrementalmente
con estado mutable — es una proyección de datos ya existentes en
transactions.parquet + users.parquet + products.parquet. El dataclass
sirve para tipar esa proyección antes de serializarla a XML, manteniendo
consistencia con el resto del proyecto.

Solo se generan instancias de Invoice para órdenes con estado_pago=APPROVED.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class InvoiceItem:
    id_producto: str
    nombre_producto: str
    cantidad: int
    precio_unitario: float
    descuento: float
    subtotal: float


@dataclass
class Invoice:
    numero_factura: str
    id_orden: str
    id_transaccion: str
    fecha_emision: datetime

    # Emisor
    nombre_tienda: str
    pais_emisor: str

    # Receptor
    nombre_completo: str
    tipo_documento: str
    numero_documento: str
    correo_electronico: str
    ciudad: str

    items: list[InvoiceItem] = field(default_factory=list)

    metodo_pago: str = ""
    metodo_entrega: str = ""
    estado_pago: str = "APPROVED"

    @property
    def subtotal_general(self) -> float:
        return round(sum(i.subtotal for i in self.items), 2)

    @property
    def descuento_total(self) -> float:
        return round(sum(i.descuento for i in self.items), 2)

    def total(self, envio_total: float) -> float:
        return round(self.subtotal_general - self.descuento_total + envio_total, 2)

    def impuestos(self) -> float:
        # IVA incluido en el precio, igual que en el evento purchase
        return round(self.subtotal_general * 0.19 / 1.19, 2)