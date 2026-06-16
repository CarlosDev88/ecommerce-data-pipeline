"""
storage/gcs.py
Implementación GCS — placeholder por ahora.
Se completa cuando el pipeline pase a producción en GCP.
"""

from pathlib import Path
from typing import Any

import pandas as pd

from storage.base import Storage


class GCSStorage(Storage):

    def __init__(self) -> None:
        raise NotImplementedError(
            "GCSStorage no está implementado aún. "
            "Usa STORAGE_BACKEND='local' en config/settings.py."
        )

    def save(self, df: pd.DataFrame, path: str | Path, **kwargs: Any) -> None:
        raise NotImplementedError

    def read(self, path: str | Path, **kwargs: Any) -> pd.DataFrame:
        raise NotImplementedError

    def exists(self, path: str | Path) -> bool:
        raise NotImplementedError