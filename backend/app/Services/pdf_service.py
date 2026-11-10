"""
PDF Generation Service
Provides zero-dependency, pure-Python generation of compliant PDF-1.4 documents
for retail transaction receipts.
"""

from typing import Dict, Any, Optional

def generate_receipt_pdf(bill_data: Dict[str, Any], store_info: Optional[Dict[str, str]] = None) -> bytes:
    """
    Generates a PDF-1.4 byte stream for a retail bill receipt.
    
    Args:
        bill_data: Dictionary containing:
            - "bill": tuple/list or dict of bill attributes
            - "items": list of item tuples/lists or dicts
        store_info: Optional store metadata (name, address, contact)
    
    Returns:
        bytes: Valid PDF-1.4 file content
    """
    bill = bill_data.get("bill", bill_data)
    items = bill_data.get("items", [])

    if isinstance(bill, (list, tuple)):
        bill_id = bill[0]
        cashier_id = bill[1]
        dt = bill[2]
        mode = bill[3]
        total = bill[4]
    elif isinstance(bill, dict):
        bill_id = bill.get("bill_id", 0)
        cashier_id = bill.get("cashier_id", 101)
        dt = bill.get("transaction_datetime", "")
        mode = bill.get("payment_mode", "Cash")
        total = bill.get("total_amount", 0.0)
    else:
        bill_id = 0
        cashier_id = 101
        dt = ""
        mode = "Cash"
        total = 0.0

    dt_str = str(dt)
    if "T" in dt_str:
        dt_str = dt_str.replace("T", " ")
    if "." in dt_str:
        dt_str = dt_str.split(".")[0]

    info = store_info or {}
    store_name = info.get("name") or "Retail Sales Intelligence Platform"
    store_addr = info.get("address")
    store_gstin = info.get("gstin")
    store_phone = info.get("phone")

    char_w = 8.0
    x_title = max(50, int(306 - (len(store_name) * char_w) / 2))

    lines = []
    y_hdr = 745
    lines.append(f"BT /F1 14 Tf {x_title} {y_hdr} Td ({store_name}) Tj ET")

    if store_addr:
        y_hdr -= 15
        x_addr = max(50, int(306 - (len(store_addr) * 4.8) / 2))
        lines.append(f"BT /F2 9 Tf {x_addr} {y_hdr} Td ({store_addr}) Tj ET")

    contact_parts = []
    if store_gstin:
        contact_parts.append(f"GSTIN: {store_gstin}")
    if store_phone:
        contact_parts.append(f"Phone: {store_phone}")
    if contact_parts:
        contact_str = " | ".join(contact_parts)
        y_hdr -= 13
        x_contact = max(50, int(306 - (len(contact_str) * 4.8) / 2))
        lines.append(f"BT /F2 9 Tf {x_contact} {y_hdr} Td ({contact_str}) Tj ET")

    # Top divider
    y_div = y_hdr - 10
    lines.append(f"0.5 w 50 {y_div} m 562 {y_div} l S")

    # Invoice Metadata
    y_meta = y_div - 18
    lines.append(f"BT /F1 11 Tf 50 {y_meta} Td (TRANSACTION RECEIPT) Tj ET")
    y_meta -= 18
    lines.append(f"BT /F1 10 Tf 50 {y_meta} Td (Bill ID: #{bill_id}) Tj ET")
    lines.append(f"BT /F2 9 Tf 220 {y_meta} Td (Date: {dt_str} IST) Tj ET")
    lines.append(f"BT /F2 9 Tf 430 {y_meta} Td (Cashier ID: #{cashier_id}) Tj ET")
    y_meta -= 14
    lines.append(f"BT /F2 9 Tf 430 {y_meta} Td (Payment Method: {mode}) Tj ET")

    # Table Header Line
    y_tbl_top = y_meta - 10
    lines.append(f"0.5 w 50 {y_tbl_top} m 562 {y_tbl_top} l S")
    lines.append(f"BT /F1 9 Tf 55 {y_tbl_top - 13} Td (ITEM / PRODUCT DESCRIPTION) Tj ET")
    lines.append(f"BT /F1 9 Tf 280 {y_tbl_top - 13} Td (QTY) Tj ET")
    lines.append(f"BT /F1 9 Tf 340 {y_tbl_top - 13} Td (PRICE) Tj ET")
    lines.append(f"BT /F1 9 Tf 410 {y_tbl_top - 13} Td (DISC) Tj ET")
    lines.append(f"BT /F1 9 Tf 490 {y_tbl_top - 13} Td (TOTAL) Tj ET")
    lines.append(f"0.5 w 50 {y_tbl_top - 20} m 562 {y_tbl_top - 20} l S")

    y = y_tbl_top - 36
    subtotal = 0.0
    total_disc = 0.0

    for it in items:
        if isinstance(it, (list, tuple)):
            name = str(it[2] if len(it) > 2 else "Item")
            qty = it[4] if len(it) > 4 else 1
            price = float(it[5] if len(it) > 5 else 0.0)
            disc = float(it[6] if len(it) > 6 else 0.0)
            line_tot = float(it[7] if len(it) > 7 else (price * qty - disc))
        elif isinstance(it, dict):
            name = str(it.get("product_name", "Item"))
            qty = it.get("quantity", 1)
            price = float(it.get("unit_price", 0.0))
            disc = float(it.get("discount", 0.0))
            line_tot = float(it.get("line_total", (price * qty - disc)))
        else:
            continue

        # Sanitize parenthesis for PDF string format
        safe_name = name.replace("(", "[").replace(")", "]")
        if len(safe_name) > 34:
            safe_name = safe_name[:32] + ".."

        subtotal += (price * qty)
        total_disc += disc

        lines.append(f"BT /F2 9 Tf 55 {y} Td ({safe_name}) Tj ET")
        lines.append(f"BT /F2 9 Tf 285 {y} Td ({qty}) Tj ET")
        lines.append(f"BT /F2 9 Tf 340 {y} Td ({price:.2f}) Tj ET")
        lines.append(f"BT /F2 9 Tf 410 {y} Td ({disc:.2f}) Tj ET")
        lines.append(f"BT /F1 9 Tf 490 {y} Td ({line_tot:.2f}) Tj ET")
        y -= 18
        if y < 130:
            break

    # Bottom Divider
    lines.append(f"0.5 w 50 {y + 6} m 562 {y + 6} l S")
    y -= 14
    lines.append(f"BT /F2 9 Tf 380 {y} Td (Subtotal: INR {subtotal:.2f}) Tj ET")
    y -= 14
    if total_disc > 0:
        lines.append(f"BT /F2 9 Tf 380 {y} Td (Total Discount: -INR {total_disc:.2f}) Tj ET")
        y -= 14
    lines.append(f"BT /F1 12 Tf 380 {y} Td (GRAND TOTAL: INR {float(total):.2f}) Tj ET")

    # Footer note
    lines.append("0.5 w 50 80 m 562 80 l S")
    lines.append("BT /F2 8 Tf 180 65 Td (Thank you for shopping with us! Please retain this receipt for returns.) Tj ET")
    lines.append("BT /F2 7 Tf 210 52 Td (Verified Digital Bill Receipt * Retail Sales Intelligence Platform) Tj ET")

    content_stream = "\n".join(lines).encode("utf-8")

    # PDF Object Assembly
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << "
            b"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
            b"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
            b">> >> >>"
        ),
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("utf-8")
        + content_stream
        + b"\nendstream",
    ]

    pdf_parts = [b"%PDF-1.4\n"]
    offsets = []
    current_offset = len(pdf_parts[0])

    for i, obj in enumerate(objects, start=1):
        offsets.append(current_offset)
        obj_header = f"{i} 0 obj\n".encode("utf-8")
        obj_footer = b"\nendobj\n"
        full_obj = obj_header + obj + obj_footer
        pdf_parts.append(full_obj)
        current_offset += len(full_obj)

    xref_offset = current_offset
    xref_table = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref_table += f"{off:010d} 00000 n \n"
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    pdf_parts.append(xref_table.encode("utf-8"))
    pdf_parts.append(trailer.encode("utf-8"))

    return b"".join(pdf_parts)

