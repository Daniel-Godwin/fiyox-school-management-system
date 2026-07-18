"""Payment receipt PDF — school-branded proof of a single payment.

Shows the payment itself plus the invoice position after it (amount, discount,
paid so far, balance, status), so a parent holding the receipt knows exactly
where they stand. It carries the school crest in the header and, in the footer,
the bursar's and principal's signatures alongside the school's official stamp —
the same branding assets used on the report card — so the receipt reads as an
official school document, not a bare printout. A5, pure reportlab.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.services.branding import data_uri_to_bytes


def _brand(hexstr: str | None) -> colors.Color:
    try:
        return colors.HexColor(hexstr)
    except Exception:
        return colors.HexColor("#0B1F3A")


def _image_flowable(uri: str | None, max_w: float, max_h: float):
    """Render a stored data-URI asset (logo/signature/stamp) at a bounded size,
    preserving aspect ratio. Returns None when the asset is absent or invalid,
    so the receipt degrades gracefully for a school that hasn't uploaded one."""
    raw = data_uri_to_bytes(uri)
    if not raw:
        return None
    try:
        reader = ImageReader(BytesIO(raw))
        iw, ih = reader.getSize()
        if not iw or not ih:
            return None
        scale = min(max_w / iw, max_h / ih)
        return Image(BytesIO(raw), width=iw * scale, height=ih * scale)
    except Exception:
        return None


def build_receipt_pdf(data: dict) -> bytes:
    """Expected keys (as passed by the fees router):
    school{name,address,state,color,logo_url,signature_url,stamp_url,principal_name},
    receipt_number, student_name, admission_number, invoice_number, method,
    reference, amount, paid_at, invoice{amount,discount,paid,balance,status},
    received_by (optional).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5,
                            topMargin=11 * mm, bottomMargin=10 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm)
    school = data["school"]
    brand = _brand(school.get("color"))
    styles = getSampleStyleSheet()
    h_school = ParagraphStyle("school", parent=styles["Title"], fontSize=13,
                              textColor=brand, spaceAfter=1, alignment=0)
    h_sub = ParagraphStyle("sub", parent=styles["Normal"], alignment=1,
                           fontSize=8, textColor=colors.grey)
    h_sub_left = ParagraphStyle("subl", parent=styles["Normal"], alignment=0,
                                fontSize=8, textColor=colors.grey)
    h_title = ParagraphStyle("rtitle", parent=styles["Normal"], alignment=1,
                             fontSize=10, spaceBefore=4, spaceAfter=6,
                             textColor=colors.white, backColor=brand)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)
    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7.5,
                               textColor=colors.grey, alignment=1)
    story = []

    # ---- header: crest + school name ----
    logo = _image_flowable(school.get("logo_url"), 18 * mm, 18 * mm)
    name_block = [Paragraph(school["name"], h_school)]
    addr = " · ".join(x for x in [school.get("address"), school.get("state")] if x)
    if addr:
        name_block.append(Paragraph(addr, h_sub_left))
    if logo:
        head = Table([[logo, name_block]], colWidths=[20 * mm, 104 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
    else:
        for f in name_block:
            story.append(f)
    story.append(Spacer(1, 3))
    story.append(Paragraph("&nbsp;OFFICIAL PAYMENT RECEIPT&nbsp;", h_title))

    method = str(data["method"]).split(".")[-1].upper()
    meta = [
        [Paragraph(f"<b>Receipt No:</b> {data['receipt_number']}", small),
         Paragraph(f"<b>Date:</b> {data['paid_at'] or ''}", small)],
        [Paragraph(f"<b>Student:</b> {data['student_name']}", small),
         Paragraph(f"<b>Admission No:</b> {data['admission_number']}", small)],
        [Paragraph(f"<b>Invoice:</b> {data['invoice_number']}", small),
         Paragraph(f"<b>Method:</b> {method} · Ref: {data['reference']}", small)],
    ]
    mt = Table(meta, colWidths=[62 * mm, 62 * mm])
    mt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # ---- the payment itself, prominent ----
    amt = Table([["AMOUNT RECEIVED", f"NGN {data['amount']:,.2f}"]],
                colWidths=[62 * mm, 62 * mm])
    amt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), brand),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(amt)
    story.append(Spacer(1, 8))

    inv = data["invoice"]
    status = str(inv["status"]).split(".")[-1].upper()
    totals = [
        ["Invoice amount", f"{inv['amount']:,.2f}"],
        ["Discount", f"{inv['discount']:,.2f}"],
        ["Total paid to date", f"{inv['paid']:,.2f}"],
        ["Outstanding balance", f"{inv['balance']:,.2f}"],
        ["Invoice status", status],
    ]
    tt = Table(totals, colWidths=[70 * mm, 40 * mm])
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 3), (-1, 3), 0.5, brand),
        ("FONTNAME", (0, 3), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(tt)
    story.append(Spacer(1, 12))

    # ---- signatures + official stamp ----
    # Left: the bursar / cashier who received the money (name over a ruled line).
    # Middle: the principal's signature image over their name.
    # Right: the school's official stamp. Any asset the school hasn't uploaded
    # simply falls back to a blank ruled line, so the receipt is never broken.
    received_by = data.get("received_by") or ""
    sig_img = _image_flowable(school.get("signature_url"), 34 * mm, 12 * mm)
    stamp_img = _image_flowable(school.get("stamp_url"), 22 * mm, 22 * mm)
    principal = school.get("principal_name") or "Principal"

    line = "____________________"

    bursar_cell = [
        Spacer(1, 12),
        Paragraph(line, sig_style),
        Paragraph(f"Received by{(': ' + received_by) if received_by else ''}", sig_style),
        Paragraph("Bursar / Cashier", sig_style),
    ]
    principal_cell = ([sig_img, Paragraph(principal, sig_style),
                       Paragraph("Principal", sig_style)]
                      if sig_img else
                      [Spacer(1, 12), Paragraph(line, sig_style),
                       Paragraph(principal, sig_style),
                       Paragraph("Principal", sig_style)])
    stamp_cell = ([stamp_img, Paragraph("Official stamp", sig_style)]
                  if stamp_img else
                  [Spacer(1, 12), Paragraph("(stamp)", sig_style)])

    foot = Table([[bursar_cell, principal_cell, stamp_cell]],
                 colWidths=[44 * mm, 44 * mm, 36 * mm])
    foot.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(foot)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Computer-generated receipt. Verified by the school stamp and signatures above.",
        h_sub))

    doc.build(story)
    return buf.getvalue()
