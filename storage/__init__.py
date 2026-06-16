"""
storage/__init__.py
Factory que instancia el backend correcto según STORAGE_BACKEND en settings.
Punto único de inyección de dependencias — el resto del código nunca
importa LocalStorage o GCSStorage directamente, solo llama get_storage().
"""

from storage.base import Storage
from config.settings import STORAGE_BACKEND


def get_storage() -> Storage:
    """
    Retorna la implementación de Storage activa.
    Cambiar STORAGE_BACKEND en settings.py es suficiente para alternar backends.
    """
    if STORAGE_BACKEND == "local":
        from storage.local import LocalStorage
        return LocalStorage()

    if STORAGE_BACKEND == "gcs":
        from storage.gcs import GCSStorage
        return GCSStorage()

    raise ValueError(f"STORAGE_BACKEND desconocido: '{STORAGE_BACKEND}'. Usa 'local' o 'gcs'.")