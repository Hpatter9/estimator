"""PDF laid out like an Xactimate estimate: room headings with dimensions, numbered line items
(DESCRIPTION / QUANTITY / UNIT PRICE / TAX / O&P / RCV), room totals, a category recap and a summary.

This is a look-alike layout for sharing/reviewing; to load the estimate into Xactimate itself you
still need to key it in (or use the Excel export as your checklist).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import Company
from ..models import Estimate, Room

SS = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=SS["Normal"], fontSize=8, leading=10)
SMALL_B = ParagraphStyle("smallb", parent=SMALL, fontName="Helvetica-Bold")
NOTE = ParagraphStyle("note", parent=SMALL, fontSize=7, textColor=colors.HexColor("#555555"), leftIndent=14)
ROOM = ParagraphStyle("room", parent=SS["Normal"], fontName="Helvetica-Bold", fontSize=10, spaceBefore=10)
RIGHT = ParagraphStyle("right", parent=SMALL, alignment=TA_RIGHT)

COLS = [3.35 * inch, 0.95 * inch, 0.75 * inch, 0.6 * inch, 0.7 * inch, 0.85 * inch]
GRID = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
    ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
])


def _m(v: float) -> str:
    return f"{v:,.2f}"


def _dims(room: Room | None) -> str:
    if not room:
        return ""
    parts = []
    if room.length_ft and room.width_ft:
        parts.append(f"{room.length_ft:g}' x {room.width_ft:g}'")
    if room.height_ft:
        parts.append(f"Height: {room.height_ft:g}'")
    for label, v in (("SF Walls", room.wall_sf), ("SF Ceiling", room.ceiling_sf), ("SF Floor", room.floor_sf),
                     ("LF Floor Perimeter", room.perimeter_lf)):
        if v:
            parts.append(f"{v:,.2f} {label}")
    return " &nbsp;&nbsp; ".join(parts)


def write_pdf(est: Estimate, path: Path, company: Company) -> Path:
    op_rate = (est.overhead_pct + est.profit_pct) / 100
    story = []

    header = [
        [Paragraph(f"<b>{company.name}</b><br/>{company.address}<br/>{company.phone} {company.email}", SMALL),
         Paragraph(f"<b>Insured:</b> {est.customer}<br/><b>Property:</b> {est.address}<br/>"
                   f"<b>Claim Number:</b> {est.claim_number}<br/><b>Type of Loss:</b> {est.loss_type}<br/>"
                   f"<b>Date:</b> {est.estimate_date:%m/%d/%Y}<br/><b>Estimate:</b> {est.title}", SMALL)],
    ]
    t = Table(header, colWidths=[3.6 * inch, 3.6 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black)]))
    story += [t, Spacer(1, 6)]
    if est.summary:
        story += [Paragraph(est.summary, SMALL), Spacer(1, 4)]

    n = 0
    recap: dict[str, float] = defaultdict(float)
    totals = {"tax": 0.0, "op": 0.0, "rcv": 0.0}
    for section in est.sections:
        rows = [["DESCRIPTION", "QUANTITY", "UNIT PRICE", "TAX", "O&P", "RCV"]]
        notes_after: dict[int, str] = {}
        s_tax = s_op = s_rcv = 0.0
        for item in section.items:
            n += 1
            ext = round(item.quantity * item.unit_price, 2)
            op = round(ext * op_rate, 2)
            rcv = round(ext + item.tax + op, 2)
            s_tax, s_op, s_rcv = s_tax + item.tax, s_op + op, s_rcv + rcv
            recap[item.category or "OTHER"] += ext
            rows.append([Paragraph(f"{n}. {item.description}", SMALL), f"{item.quantity:,.2f} {item.unit}",
                         _m(item.unit_price), _m(item.tax), _m(op), _m(rcv)])
            if item.note:
                notes_after[len(rows)] = item.note
        rows.append([Paragraph(f"<b>Totals: {section.name}</b>", SMALL), "", "", _m(s_tax), _m(s_op), _m(s_rcv)])
        for k in totals:
            totals[k] += {"tax": s_tax, "op": s_op, "rcv": s_rcv}[k]

        # notes go on their own row under the line item, spanning the table
        final_rows, spans = [], []
        for idx, row in enumerate(rows):
            final_rows.append(row)
            if idx + 1 in notes_after:
                final_rows.append([Paragraph(notes_after[idx + 1], NOTE), "", "", "", "", ""])
                spans.append(("SPAN", (0, len(final_rows) - 1), (-1, len(final_rows) - 1)))
        table = Table(final_rows, colWidths=COLS, repeatRows=1)
        table.setStyle(GRID)
        table.setStyle(TableStyle(spans + [("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
                                            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8)]))
        dims = _dims(section.room)
        story.append(KeepTogether([Paragraph(section.name, ROOM)] + ([Paragraph(dims, SMALL)] if dims else []) +
                                  [Spacer(1, 3)]))
        story.append(table)

    line_total = est.line_item_total
    grand = [["Line Item Totals", "", "", _m(totals["tax"]), _m(totals["op"]), _m(totals["rcv"])]]
    t = Table(grand, colWidths=COLS)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                           ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black)]))
    story += [Spacer(1, 8), t]

    # Recap by category
    story += [Spacer(1, 14), Paragraph("Recap by Category", ROOM)]
    rec = [["Category", "Amount", "%"]] + [
        [c, _m(v), f"{(v / line_total * 100 if line_total else 0):.2f}%"] for c, v in sorted(recap.items())]
    t = Table(rec, colWidths=[3 * inch, 1.2 * inch, 0.8 * inch])
    t.setStyle(GRID)
    story.append(t)

    # Summary
    story += [Spacer(1, 14), Paragraph("Summary", ROOM)]
    summary = [
        ["Line Item Total", _m(line_total)],
        ["Material Sales Tax", _m(est.sales_tax)],
        [f"Overhead ({est.overhead_pct:g}%)", _m(est.overhead)],
        [f"Profit ({est.profit_pct:g}%)", _m(est.profit)],
        ["Replacement Cost Value", _m(est.grand_total)],
    ]
    t = Table(summary, colWidths=[3 * inch, 1.5 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                           ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
                           ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]))
    story.append(t)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.6 * inch, 0.45 * inch, f"{est.title}  {est.estimate_date:%m/%d/%Y}")
        canvas.drawRightString(7.9 * inch, 0.45 * inch, f"Page: {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                      topMargin=0.6 * inch, bottomMargin=0.7 * inch, title=est.title).build(
        story, onFirstPage=footer, onLaterPages=footer)
    return path
