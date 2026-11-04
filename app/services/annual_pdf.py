"""Cumulative annual (end-of-session) report card PDF.

Mirrors the termly report card's letterhead and branding, but the subject grid
carries each term's total across the session plus the cumulative total, grade
and annual subject position — the document a school issues at year end.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.services.report_pdf import _brand, _image_flowable


def _fmt(v) -> str:
    return "-" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def build_annual_pdf(data: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f"Annual report - {data['student']['name']}")
    school = data["school"]
    brand = _brand(school.get("color"))
    styles = getSampleStyleSheet()

    s_name = ParagraphStyle("sname", parent=styles["Title"], fontSize=16,
                            textColor=brand, spaceAfter=0, alignment=TA_CENTER, leading=19)
    s_addr = ParagraphStyle("saddr", parent=styles["Normal"], fontSize=8,
                            textColor=colors.grey, alignment=TA_CENTER)
    s_band = ParagraphStyle("band", parent=styles["Normal"], fontSize=10,
                            alignment=TA_CENTER, textColor=colors.white, backColor=brand,
                            spaceBefore=6, spaceAfter=8, borderPadding=(4, 2, 4, 2))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=11)
    cmt = ParagraphStyle("cmt", parent=styles["Normal"], fontSize=9, leading=12)
    story = []

    # letterhead
    logo = _image_flowable(school.get("logo_url"), 22 * mm, 22 * mm)
    head_text = [Paragraph(school["name"], s_name)]
    addr = " - ".join(x for x in [school.get("address"), school.get("state")] if x)
    if addr:
        head_text.append(Paragraph(addr, s_addr))
    head_text.append(Paragraph("CUMULATIVE ANNUAL REPORT CARD", s_band))
    if logo:
        head = Table([[logo, head_text]], colWidths=[24 * mm, 158 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(head)
    else:
        story.extend(head_text)

    # student strip
    st = data["student"]
    summ = data["summary"]
    meta = [
        [Paragraph(f"<b>Name:</b> {st['name']}", small),
         Paragraph(f"<b>Admission No:</b> {st['admission_number']}", small),
         Paragraph(f"<b>Class:</b> {st['class']}", small)],
        [Paragraph(f"<b>Session:</b> {data['session']}", small),
         Paragraph(f"<b>Terms counted:</b> {summ['terms_counted']} of {summ['terms_in_session']}", small),
         Paragraph(f"<b>Class size:</b> {summ['class_size']}", small)],
    ]
    mt = Table(meta, colWidths=[74 * mm, 54 * mm, 54 * mm])
    mt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, brand),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # subject grid: Subject | <terms...> | Cumulative | Grade | Pos. | Remark
    terms = data["terms"]
    header = ["Subject"] + [t for t in terms] + ["Cumulative", "Grade", "Pos.", "Remark"]
    rows = [header]
    for r in data["subjects"]:
        rows.append([
            r["subject"],
            *[_fmt(v) for v in r["per_term"]],
            _fmt(r["cumulative"]), r["grade"], _fmt(r["position"]), r["remark"],
        ])
    n_terms = len(terms)
    widths = [40 * mm] + [16 * mm] * n_terms + [20 * mm, 13 * mm, 12 * mm]
    widths.append(max(20 * mm, 182 * mm - sum(widths)))
    grid = Table(rows, colWidths=widths, repeatRows=1)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (-3, 1), (-3, -1), "Helvetica-Bold"),  # cumulative column (before grade)
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(grid)
    story.append(Spacer(1, 8))

    # per-term averages + the annual standing
    per_term = summ.get("per_term_average") or []
    term_cells = [Paragraph(f"<b>{terms[i]}</b><br/>{_fmt(v)}{'%' if v is not None else ''}", small)
                  for i, v in enumerate(per_term)]
    summary_cells = term_cells + [
        Paragraph(f"<b>Annual average</b><br/>{_fmt(summ['cumulative_average'])}{'%' if summ['cumulative_average'] is not None else ''}", small),
        Paragraph(f"<b>Grade</b><br/>{summ['grade'] or '-'}", small),
        Paragraph(f"<b>Position</b><br/>{summ['position']} of {summ['class_size']}", small),
    ]
    n = len(summary_cells)
    ct = Table([summary_cells], colWidths=[182 * mm / n] * n)
    ct.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, brand),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F8F5")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(ct)
    story.append(Spacer(1, 10))

    # closing comments (the session's final term)
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
        ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(ctab)
    story.append(Spacer(1, 10))

    # signature + stamp
    sig = _image_flowable(school.get("signature_url"), 45 * mm, 16 * mm)
    stamp = _image_flowable(school.get("stamp_url"), 26 * mm, 26 * mm)
    principal = school.get("principal_name") or "Principal"
    sig_block = Table([[sig if sig else Spacer(1, 14 * mm)],
                       [Paragraph("_" * 34, small)],
                       [Paragraph(f"<b>{principal}</b><br/>Principal", small)]],
                      colWidths=[70 * mm])
    sig_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    foot = Table([[sig_block, stamp if stamp else Paragraph("", small)]],
                 colWidths=[120 * mm, 62 * mm])
    foot.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(foot)

    story.append(Spacer(1, 4))
    story.append(Paragraph("Generated by Fiyox School Management System.", s_addr))
    doc.build(story)
    return buf.getvalue()
