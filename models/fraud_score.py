"""
models/fraud_score.py
Dataclass tipada para el score de fraude de una orden.

Al igual que Invoice, no decide el resultado (eso ya está fijado por
TRANSACTION_STATUS_RATES en transactions.py) — solo proyecta qué reglas
de un motor antifraude real habrían explicado el rechazo, como tabla
de auditoría/explicabilidad.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FraudScore:
    id_orden: str
    id_transaccion: str
    id_usuario: str
    score_fraude: int
    nivel_confianza: str          # 'alto' | 'medio' | 'bajo'
    reglas_disparadas: list[str] = field(default_factory=list)
    monto_total_orden: float = 0.0
    fecha_transaccion: datetime = None

    def to_dict(self) -> dict:
        return {
            "id_orden": self.id_orden,
            "id_transaccion": self.id_transaccion,
            "id_usuario": self.id_usuario,
            "score_fraude": self.score_fraude,
            "nivel_confianza": self.nivel_confianza,
            "reglas_disparadas": ", ".join(self.reglas_disparadas),
            "n_reglas_disparadas": len(self.reglas_disparadas),
            "monto_total_orden": self.monto_total_orden,
            "fecha_transaccion": str(self.fecha_transaccion) if self.fecha_transaccion is not None else None,
        }