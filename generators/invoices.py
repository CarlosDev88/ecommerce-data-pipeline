"""
generators/invoices.py
Genera una factura XML por cada ORDEN con estado_pago=APPROVED, agregando
todas sus líneas de transactions.parquet. XML simplificado propio — no
pretende ser un documento válido ante la DIAN (sin CUFE, firma digital,
ni estructura UBL 2.1 real), pero usa nombres de campo inspirados en el
dominio real de facturación electrónica colombiana.

Solo se factura lo aprobado: REJECTED/PENDING/ERROR no generan factura.

Cada fila agregada de transactions.parquet se proyecta a un objeto
Invoice (models/invoice.py) antes de serializarse a XML — mismo patrón
de tipado usado en sessions.py con Session/Event.
"""

import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

import pandas as pd
from loguru import logger

from config import settings
from models.invoice import Invoice, InvoiceItem


def load_transactions(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/transactions.py")
    return pd.read_parquet(path)


def load_users(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero generators/users.py")
    return pd.read_parquet(path).set_index("id_usuario")


def load_products(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path} — corre primero el pipeline de catálogo")
    df = pd.read_parquet(path, columns=["product_id", "product_name", "source_store"])
    return df.set_index("product_id")


def _store_name(store_url: str) -> str:
    """Deriva un nombre legible de tienda desde la URL, ej. 'https://www.nike.com.co' -> 'Nike'."""
    slug = store_url.replace("https://", "").replace("www.", "").replace("co.", "").split(".")[0]
    return "Sony" if slug == "store" else slug.capitalize()


def build_invoice(order_lines: pd.DataFrame, users_lookup: pd.DataFrame, products_lookup: pd.DataFrame) -> tuple[Invoice, float]:
    """Construye el objeto Invoice tipado a partir de las líneas de una orden.
    Devuelve también envio_total por separado (no vive en InvoiceItem porque
    es un costo de orden prorrateado, no un atributo intrínseco del item)."""
    first = order_lines.iloc[0]
    id_usuario = first["id_usuario"]
    user = users_lookup.loc[id_usuario] if id_usuario in users_lookup.index else None

    # Emisor: tomamos la tienda del primer producto de la orden (simplificación —
    # en la realidad podría haber split de órdenes por tienda/seller distinto)
    primer_pid = first["id_producto"]
    store_url = products_lookup.loc[primer_pid, "source_store"] if primer_pid in products_lookup.index else "desconocida"

    items: list[InvoiceItem] = []
    envio_total = 0.0
    for _, line in order_lines.iterrows():
        pid = line["id_producto"]
        nombre_producto = products_lookup.loc[pid, "product_name"] if pid in products_lookup.index else pid
        items.append(InvoiceItem(
            id_producto=str(pid),
            nombre_producto=str(nombre_producto),
            cantidad=int(line["cantidad"]),
            precio_unitario=float(line["precio_unitario"]),
            descuento=float(line["descuento_aplicado"]),
            subtotal=float(line["subtotal_linea"]),
        ))
        envio_total += line["envio_prorrateado"]
    envio_total = round(envio_total, 2)

    invoice = Invoice(
        numero_factura=f"FE-{str(first['id_orden'])[:8].upper()}",
        id_orden=str(first["id_orden"]),
        id_transaccion=str(first["id_transaccion"]),
        fecha_emision=first["fecha_transaccion"],
        nombre_tienda=_store_name(store_url),
        pais_emisor="Colombia",
        nombre_completo=str(user["nombre_completo"]) if user is not None else "Desconocido",
        tipo_documento=str(user["tipo_documento"]) if user is not None else "",
        numero_documento=str(user["numero_documento"]) if user is not None else "",
        correo_electronico=str(user["correo_electronico"]) if user is not None else "",
        ciudad=str(user["ciudad"]) if user is not None else "",
        items=items,
        metodo_pago=str(first["metodo_pago"]),
        metodo_entrega=str(first["metodo_entrega"]),
        estado_pago=str(first["estado_pago"]),
    )
    return invoice, envio_total


def invoice_to_xml(invoice: Invoice, envio_total: float) -> ET.Element:
    root = ET.Element("factura")

    ET.SubElement(root, "numero_factura").text = invoice.numero_factura
    ET.SubElement(root, "id_orden").text = invoice.id_orden
    ET.SubElement(root, "id_transaccion").text = invoice.id_transaccion
    ET.SubElement(root, "fecha_emision").text = str(invoice.fecha_emision)

    emisor = ET.SubElement(root, "emisor")
    ET.SubElement(emisor, "nombre_tienda").text = invoice.nombre_tienda
    ET.SubElement(emisor, "pais").text = invoice.pais_emisor

    receptor = ET.SubElement(root, "receptor")
    ET.SubElement(receptor, "nombre_completo").text = invoice.nombre_completo
    ET.SubElement(receptor, "tipo_documento").text = invoice.tipo_documento
    ET.SubElement(receptor, "numero_documento").text = invoice.numero_documento
    ET.SubElement(receptor, "correo_electronico").text = invoice.correo_electronico
    ET.SubElement(receptor, "ciudad").text = invoice.ciudad

    items_el = ET.SubElement(root, "items")
    for item in invoice.items:
        item_el = ET.SubElement(items_el, "item")
        ET.SubElement(item_el, "id_producto").text = item.id_producto
        ET.SubElement(item_el, "nombre_producto").text = item.nombre_producto
        ET.SubElement(item_el, "cantidad").text = str(item.cantidad)
        ET.SubElement(item_el, "precio_unitario").text = f"{item.precio_unitario:.2f}"
        ET.SubElement(item_el, "descuento").text = f"{item.descuento:.2f}"
        ET.SubElement(item_el, "subtotal").text = f"{item.subtotal:.2f}"

    totales = ET.SubElement(root, "totales")
    ET.SubElement(totales, "subtotal_general").text = f"{invoice.subtotal_general:.2f}"
    ET.SubElement(totales, "descuento_total").text = f"{invoice.descuento_total:.2f}"
    ET.SubElement(totales, "envio_total").text = f"{envio_total:.2f}"
    ET.SubElement(totales, "impuestos").text = f"{invoice.impuestos():.2f}"
    ET.SubElement(totales, "total").text = f"{invoice.total(envio_total):.2f}"

    ET.SubElement(root, "metodo_pago").text = invoice.metodo_pago
    ET.SubElement(root, "metodo_entrega").text = invoice.metodo_entrega
    ET.SubElement(root, "estado_pago").text = invoice.estado_pago

    return root


def _pretty_xml(root: ET.Element) -> str:
    rough = ET.tostring(root, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def run() -> int:
    transactions_df = load_transactions(settings.PATHS["transactions"] / "transactions.parquet")
    users_lookup = load_users(settings.PATHS["users"] / "users.parquet")
    products_lookup = load_products(settings.PATHS["products"])

    approved = transactions_df[transactions_df["estado_pago"] == "APPROVED"]
    if approved.empty:
        logger.warning("No hay transacciones APPROVED — no se generan facturas")
        return 0

    out_dir = settings.PATHS.get("invoices") or (settings.RAW_SEMI / "invoices")
    out_dir.mkdir(parents=True, exist_ok=True)

    n_generadas = 0
    for id_orden, order_lines in approved.groupby("id_orden"):
        invoice, envio_total = build_invoice(order_lines, users_lookup, products_lookup)
        root = invoice_to_xml(invoice, envio_total)
        xml_str = _pretty_xml(root)

        out_path = out_dir / f"{id_orden}.xml"
        out_path.write_text(xml_str, encoding="utf-8")
        n_generadas += 1

    logger.success(f"{n_generadas:,} facturas XML generadas → {out_dir}")
    return n_generadas


if __name__ == "__main__":
    run()