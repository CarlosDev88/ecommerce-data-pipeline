"""
models/user.py
Dataclass tipada que representa un usuario sintético.

segmento e ingreso_segmento son inputs causales generados aquí —
no se derivan de transacciones (que aún no existen). Sesgan el
comportamiento futuro en sessions.py/transactions.py.

total_ordenes_historicas y total_gastado_historico NO se generan
aquí — son agregaciones calculadas post-transactions.parquet.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import uuid


@dataclass
class User:
    # ── Identidad y geografía ──────────────────────────────
    id_usuario: str                    # UUID4
    nombre_completo: str
    correo_electronico: str
    telefono_movil: str
    fecha_registro: datetime
    fecha_nacimiento: date
    genero: str
    ciudad: str
    pais: str
    tipo_documento: str                 # 'cedula' | 'NIT' | 'cedula_extranjeria'
    numero_documento: str

    # ── Seguridad y estado ──────────────────────────────────
    estado_cuenta: str                 # 'activo' | 'inactivo' | 'suspendido'
    verificado_email: bool
    verificado_sms: bool

    # ── Privacidad y marketing ───────────────────────────────
    acepta_habeas_data: bool
    acepta_marketing_email: bool
    canal_adquisicion: str
    dispositivo_registro: str

    # ── Comportamiento / input causal ────────────────────────
    segmento: str                      # 'estandar' | 'frecuente' | 'VIP'
    categoria_preferida_vtex: Optional[str] = None  # sampleada de products.parquet

    # ── Actividad ─────────────────────────────────────────────
    fecha_ultima_actividad: Optional[datetime] = None

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "id_usuario": self.id_usuario,
            "nombre_completo": self.nombre_completo,
            "correo_electronico": self.correo_electronico,
            "telefono_movil": self.telefono_movil,
            "fecha_registro": self.fecha_registro.isoformat(),
            "fecha_nacimiento": self.fecha_nacimiento.isoformat(),
            "genero": self.genero,
            "ciudad": self.ciudad,
            "pais": self.pais,
            "tipo_documento": self.tipo_documento,
            "numero_documento": self.numero_documento,
            "estado_cuenta": self.estado_cuenta,
            "verificado_email": self.verificado_email,
            "verificado_sms": self.verificado_sms,
            "acepta_habeas_data": self.acepta_habeas_data,
            "acepta_marketing_email": self.acepta_marketing_email,
            "canal_adquisicion": self.canal_adquisicion,
            "dispositivo_registro": self.dispositivo_registro,
            "segmento": self.segmento,
            "categoria_preferida_vtex": self.categoria_preferida_vtex,
            "fecha_ultima_actividad": self.fecha_ultima_actividad.isoformat() if self.fecha_ultima_actividad else None,
        }