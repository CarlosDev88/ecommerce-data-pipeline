"""
storage/local.py
Implementación local del contrato Storage.
Escribe y lee archivos Parquet en el sistema de archivos local bajo /data/.
"""

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from storage.base import Storage
from config.settings import PATHS


class LocalStorage(Storage):
    """
    Persiste DataFrames como Parquet comprimido (Snappy) en disco local.
    La ruta base es siempre data/raw/structured/ o data/raw/semi-structured/
    según el tipo de dato — definida en config/settings.PATHS.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        # Permite override de base_dir para tests
        self.base_dir = base_dir or PATHS["products"].parent.parent  # data/raw/structured/

    # ── save ──────────────────────────────────────────────────────────────
    def save(
        self,
        df: pd.DataFrame,
        path: str | Path,
        compression: str = "snappy",
        partition_cols: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Guarda un DataFrame como Parquet.

        Args:
            df:             DataFrame a persistir.
            path:           Ruta absoluta o relativa al archivo .parquet.
            compression:    Algoritmo de compresión — snappy (default) | gzip | zstd.
            partition_cols: Si se provee, escribe particiones tipo Hive
                            (ej: ['year', 'month', 'day']).
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if partition_cols:
            # Escribe particiones Hive: year=2024/month=01/day=15/file.parquet
            df.to_parquet(
                target.parent,
                engine="pyarrow",
                compression=compression,
                partition_cols=partition_cols,
                index=False,
            )
            logger.info(
                f"[LocalStorage] Parquet particionado → {target.parent} "
                f"({len(df):,} filas, particiones: {partition_cols})"
            )
        else:
            df.to_parquet(
                target,
                engine="pyarrow",
                compression=compression,
                index=False,
            )
            size_kb = target.stat().st_size / 1024
            logger.info(
                f"[LocalStorage] Parquet guardado → {target} "
                f"({len(df):,} filas, {size_kb:.1f} KB)"
            )

    # ── read ──────────────────────────────────────────────────────────────
    def read(
        self,
        path: str | Path,
        columns: list[str] | None = None,
        filters: list | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Lee un archivo o directorio Parquet (incluyendo particionados).

        Args:
            path:    Ruta al archivo .parquet o directorio con particiones.
            columns: Subset de columnas a leer (projection pushdown).
            filters: Filtros tipo PyArrow para partition pruning
                     (ej: [('year', '=', '2024'), ('month', '=', '01')]).
        """
        target = Path(path)

        if not target.exists():
            raise FileNotFoundError(f"[LocalStorage] No existe: {target}")

        df = pd.read_parquet(
            target,
            engine="pyarrow",
            columns=columns,
            filters=filters,
        )
        logger.info(f"[LocalStorage] Parquet leído ← {target} ({len(df):,} filas)")
        return df

    # ── exists ─────────────────────────────────────────────────────────────
    def exists(self, path: str | Path) -> bool:
        return Path(path).exists()