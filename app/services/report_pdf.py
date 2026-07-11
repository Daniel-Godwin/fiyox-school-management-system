"""Generate a school-branded terminal report-card PDF from report data.

Uses reportlab (pure Python — deploys anywhere, no system libraries).
"""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


def _brand(hexstr: str) -> colors.Color:
    try:
        return colors.HexColor(hexstr)
    except Exception:
        return colors.HexColor("#0B1F3A")


def build_report_pdf(data: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    brand = _brand(data["school"]["color"])
    styles = getSampleStyleSheet()
    h_school = ParagraphStyle("school", parent=styles["Title"], fontSize=16,
                              textColor=brand, spaceAfter=2)
    h_sub = ParagraphStyle("sub", parent=styles["Normal"], alignment=1,
                           fontSize=9, textColor=colors.grey)
    h_title = ParagraphStyle("rtitle", parent=styles["Normal"], alignment=1,
                             fontSize=11, spaceBefore=4, spaceAfter=6,
                             textColor=colors.white, backColor=brand)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)
    story = []

    # ---- Header ----
    story.append(Paragraph(data["school"]["name"], h_school))
    addr = " · ".join(x for x in [data["school"].get("address"),
                                  data["school"].get("state")] if x)
    if addr:
        story.append(Paragraph(addr, h_sub))
    term_label = {"first": "First", "second": "Second", "third": "Third"}.get(
        data["term"]["name"], data["term"]["name"].title())
    story.append(Paragraph(f"&nbsp;{term_label} Term Report Sheet&nbsp;", h_title))

    # ---- Student meta ----
    s = data["student"]; summ = data["summary"]
    meta = [[Paragraph(f"<b>Name:</b> {s['name']}", small),
             Paragraph(f"<b>Admission No:</b> {s['admission_number']}", small),
             Paragraph(f"<b>Class:</b> {s['class']}", small)],
            [Paragraph(f"<b>Position:</b> {summ['position']} of {summ['class_size']}", small),
             Paragraph(f"<b>Average:</b> {summ['average']}%", small),
             Paragraph(f"<b>Subjects:</b> {summ['subjects_count']}", small)]]
    mt = Table(meta, colWidths=[62 * mm, 60 * mm, 60 * mm])
    mt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # ---- Subject grid: dynamic component columns ----
    comp_names = [c["name"] for c in data["components"]]
    header = ["Subject"] + comp_names + ["Total", "Grade", "Pos.", "Class Avg", "Remark"]
    table_data = [header]
    for r in data["subjects"]:
        row = [r["subject"]]
        for cn in comp_names:
            row.append(r["breakdown"].get(cn, "-"))
        row += [r["total"], r["grade"], r["position"], r["class_average"], r["remark"]]
        table_data.append(row)

    ncol = len(header)
    subj_w = 42 * mm
    rest_w = (182 * mm - subj_w) / (ncol - 1)
    col_widths = [subj_w] + [rest_w] * (ncol - 1)
    grid = Table(table_data, colWidths=col_widths, repeatRows=1)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(grid)
    story.append(Spacer(1, 8))

    # ---- Affective domain (optional) ----
    if data.get("affective"):
        aff = [["Trait", "Rating"]] + [[k, v] for k, v in data["affective"].items()]
        at = Table(aff, colWidths=[60 * mm, 30 * mm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6EAF2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(at)
        story.append(Spacer(1, 8))

    # ---- Comments ----
    c = data["comments"]
    if c.get("form_teacher"):
        story.append(Paragraph(f"<b>Form Teacher's Remark:</b> {c['form_teacher']}", small))
    if c.get("principal"):
        story.append(Paragraph(f"<b>Principal's Remark:</b> {c['principal']}", small))
    if data["term"].get("next_term_begins"):
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<b>Next term begins:</b> {data['term']['next_term_begins']}", small))

    doc.build(story)
    return buf.getvalue()
