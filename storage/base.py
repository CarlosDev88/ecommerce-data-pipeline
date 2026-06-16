"""
storage/base.py
Interfaz abstracta de almacenamiento — Strategy Pattern.
Todas las implementaciones (local, GCS) deben respetar este contrato.
Cambiar el backend es inyectar una implementación diferente, nada más.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import pandas as pd


class Storage(ABC):

    @abstractmethod
    def save(self, df: pd.DataFrame, path: str | Path, **kwargs: Any) -> None:
        """
        Persiste un DataFrame en el backend correspondiente.

        Args:
            df:     DataFrame a guardar.
            path:   Ruta relativa dentro del backend (ej: 'products/products.parquet').
            kwargs: Opciones adicionales dependientes de la implementación
                    (ej: partition_cols, compression, bucket).
        """
        ...

    @abstractmethod
    def read(self, path: str | Path, **kwargs: Any) -> pd.DataFrame:
        """
        Lee datos desde el backend y retorna un DataFrame.

        Args:
            path:   Ruta relativa dentro del backend.
            kwargs: Filtros, columnas, particiones, etc.
        """
        ...

    @abstractmethod
    def exists(self, path: str | Path) -> bool:
        """Verifica si un archivo o prefijo ya existe en el backend."""
        ...