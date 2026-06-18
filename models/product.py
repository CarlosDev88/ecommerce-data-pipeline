"""
models/product.py
Dataclass tipada que representa un producto VTEX deduplicado.

Espejo directo del esquema producido por generators.extract_products.slim_product():
no agrega ni reinterpreta campos — solo le da tipos y un punto único de
serialización a Parquet. La deduplicación por EAN ocurre antes de construir
estas instancias (en dedupe_and_build.py).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    # ── Identidad ──────────────────────────────────────────────────────────
    product_id:         str
    product_name:       str
    brand:               Optional[str]
    product_reference:   Optional[str]    # SKU/referencia interna de la tienda

    # ── Categoría — se conserva para análisis "qué categoría vende más" ────
    category_id:    Optional[str]
    category_path:  Optional[str]         # ej: "/Juguetería/Lúdicos/Didácticos/"

    # ── Identificación cruzada entre tiendas ────────────────────────────────
    ean: Optional[str]                    # clave de deduplicación

    # ── Origen (tienda + búsqueda que lo encontró) ──────────────────────────
    source_store:    str
    source_keyword:  Optional[str]

    # ── Navegación ───────────────────────────────────────────────────────────
    link_text:  Optional[str]
    image_url:  Optional[str]

    # ── Precio e inventario ──────────────────────────────────────────────────
    price:               Optional[float]
    list_price:          Optional[float]   # precio sin descuento, si aplica
    available_quantity:  Optional[int]
    is_available:        Optional[bool]

    # ── Promociones y atributos flexibles — no forzamos un esquema fijo
    # de color/talla/modelo porque cada tienda VTEX expone specs distintas ──
    cluster_highlights: dict = field(default_factory=dict)
    specifications:      dict = field(default_factory=dict)

    # ── Metadata de extracción ──────────────────────────────────────────────
    extracted_at: datetime = field(default_factory=datetime.utcnow)

    # ── Helpers ─────────────────────────────────────────────────────────────
    @property
    def discount_pct(self) -> Optional[float]:
        """(list_price - price) / list_price, o None si no hay descuento."""
        if self.list_price and self.price and self.list_price > self.price:
            return round((self.list_price - self.price) / self.list_price, 4)
        return None

    @property
    def permalink(self) -> Optional[str]:
        if self.link_text:
            return f"{self.source_store}/{self.link_text}/p"
        return None

    def to_dict(self) -> dict:
        """Serializa a dict plano para escribir en Parquet."""
        return {
            "product_id":          self.product_id,
            "product_name":        self.product_name,
            "brand":                self.brand,
            "product_reference":    self.product_reference,
            "category_id":          self.category_id,
            "category_path":        self.category_path,
            "ean":                  self.ean,
            "source_store":         self.source_store,
            "source_keyword":       self.source_keyword,
            "link_text":            self.link_text,
            "permalink":            self.permalink,
            "image_url":            self.image_url,
            "price":                self.price,
            "list_price":           self.list_price,
            "discount_pct":         self.discount_pct,
            "available_quantity":   self.available_quantity,
            "is_available":         self.is_available,
            # dict -> string porque Parquet no soporta tipos anidados arbitrarios
            "cluster_highlights":   str(self.cluster_highlights) if self.cluster_highlights else None,
            "specifications":       str(self.specifications) if self.specifications else None,
            "extracted_at":         self.extracted_at.isoformat(),
        }

    @classmethod
    def from_slim(cls, slim: dict) -> "Product":
        """
        Construye un Product desde un dict ya filtrado por
        generators.extract_products.slim_product().
        """
        return cls(
            product_id          = str(slim.get("productId", "")),
            product_name        = slim.get("productName", ""),
            brand                = slim.get("brand"),
            product_reference    = slim.get("productReference"),
            category_id          = str(slim.get("categoryId")) if slim.get("categoryId") else None,
            category_path        = slim.get("categoryPath"),
            ean                  = slim.get("ean"),
            source_store         = slim.get("_source_store", ""),
            source_keyword       = slim.get("_source_keyword"),
            link_text            = slim.get("linkText"),
            image_url            = slim.get("imageUrl"),
            price                = float(slim["price"]) if slim.get("price") else None,
            list_price           = float(slim["listPrice"]) if slim.get("listPrice") else None,
            available_quantity   = int(slim["availableQuantity"]) if slim.get("availableQuantity") is not None else None,
            is_available         = slim.get("isAvailable"),
            cluster_highlights   = slim.get("clusterHighlights") or {},
            specifications       = slim.get("specifications") or {},
        )