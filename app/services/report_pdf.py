"""Report card PDF — the document a parent actually holds.

Design intent: a Nigerian secondary-school report sheet a principal would be
happy to sign — school crest and name at the top, the subject grid as the
centre of gravity, a summary that places the child against the class, then the
two comments that give the numbers meaning, closed by the principal's
signature and the school stamp.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
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


def build_report_pdf(data: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f"Report card - {data['student']['name']}")
    school = data["school"]
    brand = _brand(school.get("color"))
    styles = getSampleStyleSheet()

    s_name = ParagraphStyle("sname", parent=styles["Title"], fontSize=16,
                            textColor=brand, spaceAfter=0, alignment=TA_CENTER,
                            leading=19)
    s_addr = ParagraphStyle("saddr", parent=styles["Normal"], fontSize=8,
                            textColor=colors.grey, alignment=TA_CENTER)
    s_band = ParagraphStyle("band", parent=styles["Normal"], fontSize=10,
                            alignment=TA_CENTER, textColor=colors.white,
                            backColor=brand, spaceBefore=6, spaceAfter=8,
                            borderPadding=(4, 2, 4, 2))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5,
                           leading=11)
    cmt = ParagraphStyle("cmt", parent=styles["Normal"], fontSize=9, leading=12)
    story = []

    # letterhead
    logo = _image_flowable(school.get("logo_url"), 22 * mm, 22 * mm)
    head_text = [Paragraph(school["name"], s_name)]
    addr = " - ".join(x for x in [school.get("address"), school.get("state")] if x)
    if addr:
        head_text.append(Paragraph(addr, s_addr))
    head_text.append(Paragraph("STUDENT REPORT CARD", s_band))

    if logo:
        head = Table([[logo, head_text]], colWidths=[24 * mm, 158 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
    else:
        story.extend(head_text)

    # student strip
    st = data["student"]
    summ = data["summary"]
    term_name = str(data["term"]["name"]).split(".")[-1].title()
    meta = [
        [Paragraph(f"<b>Name:</b> {st['name']}", small),
         Paragraph(f"<b>Admission No:</b> {st['admission_number']}", small),
         Paragraph(f"<b>Class:</b> {st['class']}", small)],
        [Paragraph(f"<b>Term:</b> {term_name}", small),
         Paragraph(f"<b>Subjects:</b> {summ['subjects_count']}", small),
         Paragraph(f"<b>Class size:</b> {summ['class_size']}", small)],
    ]
    mt = Table(meta, colWidths=[74 * mm, 54 * mm, 54 * mm])
    mt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, brand),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # subject grid
    comps = [c["name"] for c in data["components"]]
    header = ["Subject"] + [f"{c['name']}\n/{c['max']}" for c in data["components"]] + [
        "Total\n/100", "Grade", "Class\nAvg.", "Pos.", "Remark"]
    rows = [header]
    for r in data["subjects"]:
        bd = r["breakdown"] or {}
        rows.append([
            r["subject"],
            *[str(bd.get(c, "-")) for c in comps],
            str(r["total"]), r["grade"], str(r["class_average"]),
            str(r["position"]), r["remark"],
        ])

    n_comp = len(comps)
    widths = [38 * mm] + [13 * mm] * n_comp + [13 * mm, 12 * mm, 14 * mm, 10 * mm]
    widths.append(max(20 * mm, 182 * mm - sum(widths)))

    grid = Table(rows, colWidths=widths, repeatRows=1)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, 0), 8.5),
        ("ALIGN", (1, 0), (-2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F6FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(grid)
    story.append(Spacer(1, 8))

    # summary: the child against the class
    class_avg = summ.get("class_average") or 0
    delta = round(summ["average"] - class_avg, 1) if class_avg else 0
    if not class_avg:
        stand = "-"
    elif delta > 0:
        stand = f"{delta:+.1f} above class average"
    elif delta < 0:
        stand = f"{delta:.1f} below class average"
    else:
        stand = "at the class average"

    cards = [[
        Paragraph(f"<b>Total</b><br/>{summ['grand_total']}", small),
        Paragraph(f"<b>Average</b><br/>{summ['average']}%", small),
        Paragraph(f"<b>Class average</b><br/>{class_avg}%", small),
        Paragraph(f"<b>Position</b><br/>{summ['position']} of {summ['class_size']}", small),
        Paragraph(f"<b>Standing</b><br/>{stand}", small),
    ]]
    ct = Table(cards, colWidths=[28 * mm, 30 * mm, 34 * mm, 36 * mm, 54 * mm])
    ct.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, brand),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F8F5")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(ct)
    story.append(Spacer(1, 8))

    # affective domain (optional)
    aff = data.get("affective") or {}
    if aff:
        arows = [["Behaviour", "Rating"]] + [[k, str(v)] for k, v in aff.items()]
        at = Table(arows, colWidths=[60 * mm, 25 * mm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EAF0")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(at)
        story.append(Spacer(1, 8))

    # comments
    comments = data.get("comments") or {}
    ft = comments.get("form_teacher") or "-"
    pc = comments.get("principal") or "-"
    crows = [
        [Paragraph("<b>Form teacher's comment</b>", small)],
        [Paragraph(ft, cmt)],
        [Paragraph("<b>Principal's comment</b>", small)],
        [Paragraph(pc, cmt)],
    ]
    ctab = Table(crows, colWidths=[182 * mm])
    ctab.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, brand),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E7EAF0")),
        ("BACKGROUND", (0, 2), (0, 2), colors.HexColor("#E7EAF0")),
        ("LINEBELOW", (0, 1), (0, 1), 0.25, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ctab)
    story.append(Spacer(1, 10))

    # signature + stamp
    sig = _image_flowable(school.get("signature_url"), 45 * mm, 16 * mm)
    stamp = _image_flowable(school.get("stamp_url"), 26 * mm, 26 * mm)
    principal = school.get("principal_name") or "Principal"

    sig_top = sig if sig else Spacer(1, 14 * mm)
    sig_block = Table([[sig_top],
                       [Paragraph("_" * 34, small)],
                       [Paragraph(f"<b>{principal}</b><br/>Principal", small)]],
                      colWidths=[70 * mm])
    sig_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    stamp_cell = stamp if stamp else Paragraph("", small)
    foot = Table([[sig_block, stamp_cell]], colWidths=[120 * mm, 62 * mm])
    foot.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(foot)

    nxt = data["term"].get("next_term_begins")
    if nxt:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Next term begins:</b> {nxt}", small))

    story.append(Spacer(1, 4))
    story.append(Paragraph("Generated by Fiyox School Management System.", s_addr))

    doc.build(story)
    return buf.getvalue()
