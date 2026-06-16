"""
models/product.py
Dataclass tipada que representa un producto extraído de MercadoLibre Colombia.
Todos los campos son opcionales excepto item_id y title — la API no garantiza
que todos los atributos estén presentes en cada publicación.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    # ── Identidad ──────────────────────────────────────────────────────────
    item_id:        str
    title:          str
    category_id:    str
    category_name:  str
    status:         str                     # active | paused | closed

    # ── Precio ─────────────────────────────────────────────────────────────
    price_cop:          float
    original_price_cop: Optional[float]     # None si no tiene descuento
    discount_pct:       Optional[float]     # (original - price) / original
    currency_id:        str                 # siempre COP en MCO

    # ── Inventario & popularidad ────────────────────────────────────────────
    available_quantity: int
    sold_quantity:      int
    listing_type_id:    str                 # gold_special | gold_pro | classic | free

    # ── Seller ─────────────────────────────────────────────────────────────
    seller_id:        int
    seller_nickname:  str
    seller_city:      Optional[str]
    seller_state:     Optional[str]

    # ── Logística ──────────────────────────────────────────────────────────
    free_shipping:    bool
    logistic_type:    Optional[str]         # fulfillment | cross_docking | not_specified
    accepts_mercadopago: bool

    # ── Atributos de producto (extraídos de attributes[]) ──────────────────
    brand:  Optional[str]
    model:  Optional[str]
    color:  Optional[str]
    size:   Optional[str]
    gtin:   Optional[str]                   # código de barras universal

    # ── Engagement (de /reviews/item/{id} — solo top 20%) ──────────────────
    rating_average: Optional[float]         # 1.0 – 5.0
    ratings_total:  Optional[int]

    # ── Multimedia & tracking ───────────────────────────────────────────────
    thumbnail_url:  Optional[str]
    picture_urls:   list[str] = field(default_factory=list)  # hasta 3 imágenes
    permalink:      Optional[str] = None

    # ── Metadata de extracción ──────────────────────────────────────────────
    date_created:   Optional[datetime] = None
    last_updated:   Optional[datetime] = None
    extracted_at:   datetime = field(default_factory=datetime.utcnow)

    # ── Helpers ─────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serializa a dict plano para escribir en Parquet/JSON."""
        return {
            # Identidad
            "item_id":              self.item_id,
            "title":                self.title,
            "category_id":          self.category_id,
            "category_name":        self.category_name,
            "status":               self.status,
            # Precio
            "price_cop":            self.price_cop,
            "original_price_cop":   self.original_price_cop,
            "discount_pct":         self.discount_pct,
            "currency_id":          self.currency_id,
            # Inventario
            "available_quantity":   self.available_quantity,
            "sold_quantity":        self.sold_quantity,
            "listing_type_id":      self.listing_type_id,
            # Seller
            "seller_id":            self.seller_id,
            "seller_nickname":      self.seller_nickname,
            "seller_city":          self.seller_city,
            "seller_state":         self.seller_state,
            # Logística
            "free_shipping":        self.free_shipping,
            "logistic_type":        self.logistic_type,
            "accepts_mercadopago":  self.accepts_mercadopago,
            # Atributos
            "brand":                self.brand,
            "model":                self.model,
            "color":                self.color,
            "size":                 self.size,
            "gtin":                 self.gtin,
            # Engagement
            "rating_average":       self.rating_average,
            "ratings_total":        self.ratings_total,
            # Multimedia
            "thumbnail_url":        self.thumbnail_url,
            "picture_urls":         ",".join(self.picture_urls),  # Parquet no soporta list nativo
            "permalink":            self.permalink,
            # Metadata
            "date_created":         self.date_created.isoformat() if self.date_created else None,
            "last_updated":         self.last_updated.isoformat() if self.last_updated else None,
            "extracted_at":         self.extracted_at.isoformat(),
        }

    @classmethod
    def from_ml_response(
        cls,
        item: dict,
        category_name: str,
        rating_average: Optional[float] = None,
        ratings_total: Optional[int] = None,
    ) -> "Product":
        """
        Construye un Product desde la respuesta raw de /items/{id}.
        Centraliza toda la lógica de extracción y normalización aquí
        para que generators/products.py solo llame este método.
        """
        # Precio y descuento
        price         = float(item.get("price") or 0)
        original      = item.get("original_price")
        original_f    = float(original) if original else None
        discount_pct  = round((original_f - price) / original_f, 4) if original_f and original_f > price else None

        # Atributos dinámicos — cada categoría tiene los suyos
        attrs: dict[str, str] = {
            a["id"]: a.get("value_name", "")
            for a in item.get("attributes", [])
            if a.get("value_name")
        }

        # Shipping
        shipping      = item.get("shipping", {})
        free_shipping = shipping.get("free_shipping", False)
        logistic_type = shipping.get("logistic_type")

        # Seller address
        seller_addr   = item.get("seller_address", {})
        seller_city   = seller_addr.get("city", {}).get("name")
        seller_state  = seller_addr.get("state", {}).get("name")

        # Imágenes — tomamos hasta 3
        pictures = [
            p["url"]
            for p in item.get("pictures", [])[:3]
            if p.get("url")
        ]

        # Fechas
        def _parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                return None

        return cls(
            item_id             = item["id"],
            title               = item.get("title", ""),
            category_id         = item.get("category_id", ""),
            category_name       = category_name,
            status              = item.get("status", "active"),
            price_cop           = price,
            original_price_cop  = original_f,
            discount_pct        = discount_pct,
            currency_id         = item.get("currency_id", "COP"),
            available_quantity  = item.get("available_quantity", 0),
            sold_quantity       = item.get("sold_quantity", 0),
            listing_type_id     = item.get("listing_type_id", ""),
            seller_id           = item.get("seller_id", 0),
            seller_nickname     = item.get("seller", {}).get("nickname", ""),
            seller_city         = seller_city,
            seller_state        = seller_state,
            free_shipping       = free_shipping,
            logistic_type       = logistic_type,
            accepts_mercadopago = item.get("accepts_mercadopago", False),
            brand               = attrs.get("BRAND"),
            model               = attrs.get("MODEL"),
            color               = attrs.get("COLOR"),
            size                = attrs.get("SIZE"),
            gtin                = attrs.get("GTIN"),
            rating_average      = rating_average,
            ratings_total       = ratings_total,
            thumbnail_url       = item.get("thumbnail"),
            picture_urls        = pictures,
            permalink           = item.get("permalink"),
            date_created        = _parse_dt(item.get("date_created")),
            last_updated        = _parse_dt(item.get("last_updated")),
        )