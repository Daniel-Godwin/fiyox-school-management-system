"""Render a termly class score sheet (broadsheet) as a landscape PDF.

One page (or more, with the header repeated) carrying every student in the class
down the rows and every subject across the columns. Subjects are numbered S1…Sn
in the header to keep the grid narrow; a legend under the table maps each code to
its full subject name. Totals, average, grade and position close each row.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.report_pdf import _brand, _image_flowable


def _fmt(v) -> str:
    return "-" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def build_broadsheet_pdf(data: dict) -> bytes:
    buf = BytesIO()
    page = landscape(A4)                     # 297 x 210 mm
    doc = SimpleDocTemplate(buf, pagesize=page,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            title=f"Score sheet - {data['class']} - {data['term']} term")
    school = data["school"]
    brand = _brand(school.get("color"))
    styles = getSampleStyleSheet()
    usable = page[0] - 20 * mm               # width inside the margins

    s_name = ParagraphStyle("sname", parent=styles["Title"], fontSize=15,
                            textColor=brand, spaceAfter=0, alignment=TA_CENTER, leading=18)
    s_addr = ParagraphStyle("saddr", parent=styles["Normal"], fontSize=8,
                            textColor=colors.grey, alignment=TA_CENTER)
    s_band = ParagraphStyle("band", parent=styles["Normal"], fontSize=10,
                            alignment=TA_CENTER, textColor=colors.white, backColor=brand,
                            spaceBefore=5, spaceAfter=6, borderPadding=(4, 2, 4, 2))
    legend = ParagraphStyle("legend", parent=styles["Normal"], fontSize=8, leading=11)
    nm = ParagraphStyle("nm", parent=styles["Normal"], fontSize=7.5, leading=9)
    story = []

    # letterhead
    logo = _image_flowable(school.get("logo_url"), 20 * mm, 20 * mm)
    head_text = [Paragraph(school["name"], s_name)]
    addr = " - ".join(x for x in [school.get("address"), school.get("state")] if x)
    if addr:
        head_text.append(Paragraph(addr, s_addr))
    band = f"CLASS SCORE SHEET &nbsp;·&nbsp; {data['class']} &nbsp;·&nbsp; {data['term']} Term"
    if data.get("session"):
        band += f" &nbsp;·&nbsp; {data['session']}"
    head_text.append(Paragraph(band, s_band))
    if logo:
        head = Table([[logo, head_text]], colWidths=[22 * mm, usable - 22 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(head)
    else:
        story.extend(head_text)

    subjects = data["subjects"]
    n = len(subjects)
    codes = [f"S{i + 1}" for i in range(n)]

    # column widths: fixed ends, subjects share the middle
    w_idx, w_tot, w_avg, w_grd, w_pos = 8 * mm, 15 * mm, 14 * mm, 11 * mm, 11 * mm
    tail = w_tot + w_avg + w_grd + w_pos
    w_name = 46 * mm
    w_sub = (usable - w_idx - w_name - tail) / n if n else 14 * mm
    w_sub = max(7 * mm, min(16 * mm, w_sub))
    # if the subjects are many, let the name column give up space to keep the fit
    overflow = (w_idx + w_name + n * w_sub + tail) - usable
    if overflow > 0:
        w_name = max(30 * mm, w_name - overflow)

    header = ["#", "Student"] + codes + ["Total", "Avg", "Grd", "Pos"]
    table_rows = [header]
    for i, r in enumerate(data["rows"], start=1):
        table_rows.append([
            str(i),
            Paragraph(r["name"], nm),
            *[_fmt(v) for v in r["scores"]],
            _fmt(r["grand_total"]),
            _fmt(r["average"]),
            r["grade"] or "-",
            str(r["position"]) if r["computed"] and r["position"] else "-",
        ])
    # class average footer row
    avg_cells = [_fmt(v) for v in data.get("subject_averages", [])]
    table_rows.append(["Class average", "", *avg_cells, "",
                       _fmt(data.get("class_average")), "", ""])

    widths = [w_idx, w_name] + [w_sub] * n + [w_tot, w_avg, w_grd, w_pos]
    grid = Table(table_rows, colWidths=widths, repeatRows=1)
    last = len(table_rows) - 1
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, last - 1), [colors.white, colors.HexColor("#F4F6FA")]),
        ("FONTNAME", (-4, 1), (-1, -1), "Helvetica-Bold"),   # total/avg/grd/pos
        # class-average footer
        ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#EEF1F6")),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
        ("SPAN", (0, last), (1, last)),
        ("ALIGN", (0, last), (1, last), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (1, 0), (1, -1), 4)]))
    story.append(grid)
    story.append(Spacer(1, 6))

    # subject legend: S1 = Mathematics · S2 = English · …
    if subjects:
        parts = [f"<b>{codes[i]}</b> {subjects[i]['name']}" for i in range(n)]
        story.append(Paragraph(" &nbsp;·&nbsp; ".join(parts), legend))
        story.append(Spacer(1, 4))

    footer = (f"Students: {data['class_size']} &nbsp;·&nbsp; "
              f"Computed: {data['computed_count']} &nbsp;·&nbsp; "
              f"Generated by Fiyox School Management System.")
    story.append(Paragraph(footer, s_addr))
    doc.build(story)
    return buf.getvalue()
