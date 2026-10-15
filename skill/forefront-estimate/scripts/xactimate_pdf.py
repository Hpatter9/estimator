"""Forefront's Xactimate-style PDF, laid out like the estimates Forefront sends from Xactimate.

Pages, in order (matching a real Forefront Xactimate export):
  1-2   Cover: letterhead, client / estimator block, price list, Total Estimate, deposit line, policy wording
  3+    Line items: "<ESTIMATE>" / "Source - DocuSketchConverter", General Conditions, then each level
        ("1st Floor") with every room: dimension block, then items grouped under italic sub-headings
        (Drywall, Paint, Baseboard, Snaplock Laminate, Carpet, Doors and Casing, Cleaning ...),
        "Totals: <room>", "Total: <level>", Labor Minimums Applied, "Line Item Totals: <ESTIMATE>"
        Grand Total Areas
        Recap by Room
        Recap by Category
        Sketch pages (landscape), one per floor plan image in estimate.json "sketches"

Everything company-specific comes from company.json -> "xactimate".
render.py calls render_xactimate(job, company, path).
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

PW, PH = letter
PT = 0.72                      # template measured in 850px-wide page images -> points
LM = 36                        # left margin of the body
RM = PW - 36                   # right edge of the body
BODY_W = RM - LM
TOP = PH - 133                 # body starts under the letterhead
BOTTOM = 80                    # above the footer

F, FB, FI, FBI = "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"


def St(name, **kw):
    base = dict(fontName=F, fontSize=10, leading=12, textColor=colors.black)
    base.update(kw)
    return ParagraphStyle(name, **base)


P = St("p", spaceAfter=10)
CELL = St("cell", fontSize=9.5, leading=11)
NOTE = St("note", fontSize=9.5, leading=11.5)
GROUP = St("group", fontName=FBI, fontSize=9.5, leading=11)
CENTER_B = St("cb", fontName=FB, fontSize=11, leading=14, alignment=TA_CENTER)
CENTER_B14 = St("cb14", fontName=FB, fontSize=13, leading=16, alignment=TA_CENTER)


def esc(s) -> str:
    return escape(str(s or ""))


def n2(v: float) -> str:
    return f"{v:,.2f}"


# ---------------------------------------------------------------- groups and categories

# Sub-headings inside a room, in print order. First keyword hit wins (checked in RULES order).
GROUP_ORDER = ["General", "Demolition", "Framing", "Insulation", "Drywall", "Electrical", "Light Fixtures", "Plumbing",
               "Tub and Surround", "Vanity", "Cabinets", "Appliances", "Paint", "Baseboard", "Snaplock Laminate",
               "Vinyl Plank", "Hardwood", "Carpet", "Tile", "Doors and Casing", "Window Trim", "Shelving",
               "Mirrors", "Bath Accessories", "HVAC", "Contents", "Cleaning"]

GROUP_RULES = [
    ("Cleaning", ["final cleaning", "clean floor", "clean the", "clean and deodorize", "cleaning"]),
    ("Baseboard", ["baseboard", "quarter round", "base shoe", "cove base"]),
    ("Doors and Casing", ["door", "casing", "knob", "lockset", "bifold", "bypass", "jamb"]),
    ("Window Trim", ["window stool", "stool & apron", "window sill"]),
    ("Snaplock Laminate", ["laminate", "floor protection", "t- molding", "t-molding", "reducer", "clean and prep floor",
                           "underlayment - rubber", "underlayment - foam"]),
    ("Vinyl Plank", ["vinyl plank", "floor preparation for resilient", "vinyl - metal transition"]),
    ("Hardwood", ["wood flooring", "oak flooring", "sand, stain", "dustless floor"]),
    ("Carpet", ["carpet", "tackless", "scrape rubber"]),
    ("Tub and Surround", ["tub surround", "cement board", "waterproof membrane", "caulking - silicone",
                          "tub/shower faucet", "shower faucet", "bathtub"]),
    ("Vanity", ["vanity"]),
    ("Cabinets", ["cabinet", "countertop", "toe kick"]),
    ("Mirrors", ["mirror"]),
    ("Bath Accessories", ["towel", "toilet paper", "grab bar", "soap dish", "robe hook"]),
    ("Shelving", ["shelf", "shelving", "closet rod"]),
    ("Tile", ["tile", "grout"]),
    ("Plumbing", ["toilet", "angle stop", "supply line", "p-trap", "faucet", "sink", "disposer", "plumbing"]),
    ("Appliances", ["refrigerator", "dishwasher", "range", "washer", "dryer", "microwave"]),
    ("HVAC", ["heat/ac", "register", "furnace", "ductwork", "diffuser", "cold air return", "hvac"]),
    ("Light Fixtures", ["light fixture"]),
    ("Electrical", ["outlet", "switch", "smoke detector", "electrician", "wiring", "ventilation fan", "exhaust fan",
                    "gfi", "electrical"]),
    ("Insulation", ["insulation"]),
    ("Paint", ["paint", "seal/prime", "seal the", "seal (", "seal &", "mask and prep", "mask the floor",
               "mask and cover", "stain blocker", "primer"]),
    ("Drywall", ["drywall", "texture", "water rock", "tape joint", "mask per square foot", "mask wall",
                 "skim coat", "corner bead"]),
    ("Framing", ["stud", "framing", "sheathing", "furring", "lumber"]),
    ("Contents", ["contents", "content manipulation"]),
    ("Demolition", ["tear out", "remove "]),
    ("General", ["haul debris", "supervision", "dumpster", "permit", "dust containment", "labor minimum",
                 "equipment", "protection"]),
]

# Xactimate category for "Recap by Category".
CATEGORY_RULES = [
    ("CLEANING", ["final cleaning", "clean floor", "clean the", "clean and"]),
    ("FLOOR COVERING - CARPET", ["carpet", "tackless", "scrape rubber"]),
    ("FLOOR COVERING - LAMINATE - SIMULATED WOOD", ["laminate", "floor protection", "t- molding", "t-molding", "underlayment - rubber",
                                                   "clean and prep floor", "reducer"]),
    ("FLOOR COVERING - VINYL", ["vinyl plank", "resilient", "vinyl - metal"]),
    ("FLOOR COVERING - WOOD", ["wood flooring", "oak flooring", "sand, stain"]),
    ("FLOOR COVERING - CERAMIC TILE", ["tile floor", "clean floor - tile"]),
    ("TILE", ["tub surround", "ceramic/porcelain tile", "cement board", "waterproof membrane", "tile"]),
    ("MIRRORS & SHOWER DOORS", ["mirror"]),
    ("TOILET & BATH ACCESSORIES", ["towel", "toilet paper", "grab bar"]),
    ("CABINETRY", ["cabinet", "vanity", "countertop", "toe kick"]),
    ("FINISH CARPENTRY / TRIMWORK", ["baseboard", "casing", "quarter round", "window stool", "closet shelf",
                                     "shelving", "base shoe"]),
    ("INTERIOR DOORS", ["door unit", "bifold door set", "bypass", "slab only - detach", "interior door"]),
    ("FINISH HARDWARE", ["door knob", "lockset", "hinge"]),
    ("PAINTING", ["paint", "seal/prime", "seal the", "seal (", "seal &", "mask and prep", "mask the floor",
                  "mask and cover", "stain blocker"]),
    ("DRYWALL", ["drywall", "texture", "water rock", "tape joint", "mask per square foot", "mask wall"]),
    ("INSULATION", ["insulation"]),
    ("PLUMBING", ["toilet", "angle stop", "supply line", "p-trap", "faucet", "sink", "disposer"]),
    ("HEAT, VENT & AIR CONDITIONING", ["heat/ac", "register", "furnace", "ductwork", "diffuser"]),
    ("LIGHT FIXTURES", ["light fixture"]),
    ("ELECTRICAL", ["outlet", "switch", "smoke detector", "electrician", "wiring", "ventilation fan", "gfi"]),
    ("APPLIANCES", ["refrigerator", "dishwasher", "range", "washer", "dryer"]),
    ("CONTENT MANIPULATION", ["contents", "content manipulation"]),
    ("FRAMING & ROUGH CARPENTRY", ["stud", "framing", "sheathing", "furring"]),
    ("PERMITS AND FEES", ["permit"]),
    ("GENERAL DEMOLITION", ["haul debris", "tear out", "remove ", "dumpster"]),
    ("LABOR ONLY", ["supervision", "per hour", "labor minimum"]),
]


def classify(desc: str, rules, default: str) -> str:
    d = desc.lower()
    for name, words in rules:
        if any(w in d for w in words):
            return name
    return default


def group_of(i) -> str:
    return i.get("group") or classify(i["description"], GROUP_RULES, "General")


def category_of(i) -> str:
    return i.get("category") or classify(i["description"], CATEGORY_RULES, "GENERAL DEMOLITION")


def removal(desc: str) -> bool:
    d = desc.lower()
    return d.startswith("remove ") or d.startswith("tear out")


# ---------------------------------------------------------------- page furniture

class Pages:
    def __init__(self, company: dict, est_name: str, date_s: str):
        self.x = company.get("xactimate", {})
        self.c = company
        self.est = est_name
        self.date_s = date_s
        logo = ASSETS / self.x.get("logo", "xact_logo.png")
        self.logo = ImageReader(str(logo)) if logo.exists() else None

    def letterhead(self, c):
        x = self.x
        if self.logo:
            c.drawImage(self.logo, 45 * PT, PH - 138 * PT, width=81 * PT, height=81 * PT, mask="auto")
        c.setFont(FB, 12)
        c.drawString(144 * PT, PH - 74 * PT, x.get("company_title", self.c.get("legal_name", "")))
        c.setLineWidth(0.6)
        c.line(144 * PT, PH - 83 * PT, 816 * PT, PH - 83 * PT)
        c.setFont(F, 9.5)
        lines = [x.get("office_label", "")] + x.get("address_lines", []) + [x.get("phone", "")]
        if x.get("iicrc"):
            lines.append(f"IICRC: {x['iicrc']}")
        y = PH - 102 * PT
        for ln in lines:
            c.drawString(144 * PT, y, ln)
            y -= 15.5 * PT

    def footer(self, c, doc, wide=False):
        c.setFont(F, 9.5)
        w = landscape(letter)[0] if wide else PW
        y = 66 if not wide else 0.38 * inch
        c.drawString(38 * PT, y, self.est)
        c.drawString(w - 207 * PT, y, self.date_s)
        c.drawRightString(w - 36 * PT, y, f"Page: {doc.page}")

    def portrait(self, c, doc):
        c.saveState()
        self.letterhead(c)
        self.footer(c, doc)
        c.restoreState()


# ---------------------------------------------------------------- tables

COLS = [2.85 * inch, 0.95 * inch, 0.75 * inch, 0.85 * inch, 0.8 * inch, 0.8 * inch, 0.84 * inch]
HEAD = ["DESCRIPTION", "QTY", "REMOVE", "REPLACE", "TAX", "O&P", "TOTAL"]


def head_row():
    return [Paragraph(f"<b>{esc(h)}</b>", St("h" + h, fontName=FB, fontSize=9.5, leading=11,
                                        alignment=TA_RIGHT if k else 0)) for k, h in enumerate(HEAD)]


def items_table(rows, styles):
    t = Table(rows, colWidths=COLS, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), F, 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ] + styles))
    return t


def section_title(name: str, right: str = "") -> Table:
    t = Table([[Paragraph(f"<b>{esc(name)}</b>", St("st", fontName=FB, fontSize=10.5, leading=13)),
                Paragraph(f"<b>{esc(right)}</b>", St("str", fontName=FB, fontSize=10.5, leading=13,
                                                     alignment=TA_RIGHT))]],
              colWidths=[BODY_W - 165 * PT * 0 - 2.6 * inch - 1.4 * inch, 1.4 * inch])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    outer = Table([["", t]], colWidths=[2.6 * inch, BODY_W - 2.6 * inch])
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def dims_block(r: dict) -> list:
    floor = float(r.get("floor_sf") or 0)
    ceil = float(r.get("ceiling_sf") or floor)
    walls = float(r.get("wall_sf") or 0)
    fp = float(r.get("floor_perimeter_lf") or 0)
    cp = float(r.get("ceiling_perimeter_lf") or fp)
    left = [(walls, "SF Walls"), (walls + ceil, "SF Walls & Ceiling"), (floor / 9, "SY Flooring"), (cp, "LF Ceil. Perimeter")]
    right = [(ceil, "SF Ceiling"), (floor, "SF Floor"), (fp, "LF Floor Perimeter"), None]
    rows = []
    for a, b in zip(left, right):
        rows.append(["", n2(a[0]), a[1], n2(b[0]) if b else "", b[1] if b else ""])
    t = Table(rows, colWidths=[2.6 * inch, 1.3 * inch, 1.55 * inch, 1.05 * inch, BODY_W - 6.5 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), F, 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                           ("ALIGN", (3, 0), (3, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return [t]


def total_line(label: str, tax: float, op: float, total: float, double=True, bold=False):
    f = FB if bold else F
    t = Table([[label, "", "", "", n2(tax), n2(op), n2(total)]], colWidths=COLS)
    st = [("FONT", (0, 0), (-1, -1), f, 9.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
          ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]
    if double:
        st += [("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black)]
    t.setStyle(TableStyle(st))
    if double:
        rule = Table([[""]], colWidths=[BODY_W], rowHeights=[2])
        rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black)]))
        return [rule, t]
    return [t]


# ---------------------------------------------------------------- main renderer

def render_xactimate(job, company: dict, path: Path):
    d = job.d
    x = {**company.get("xactimate", {}), **(d.get("xactimate") or {})}
    est = d.get("estimate_number") or "ESTIMATE"
    date_s = f"{job.date.month}/{job.date.day}/{job.date.year}"
    pages = Pages(company, est, date_s)
    oh_pct = float(d.get("overhead_pct", company.get("overhead_pct", 10)))
    pr_pct = float(d.get("profit_pct", company.get("profit_pct", 10)))
    rooms = {r["name"].lower(): r for r in d.get("rooms", []) if r.get("name")}
    source = x.get("source_area", "Source - DocuSketchConverter")

    # ---- numbers
    line_total = sum(job.ext(i) for _, i in job.items())
    op_total = sum(job.op(i) for _, i in job.items())
    tax_total = sum(float(i.get("tax", 0) or 0) for _, i in job.items())
    overhead = round(op_total * oh_pct / (oh_pct + pr_pct), 2) if oh_pct + pr_pct else 0.0
    profit = round(op_total - overhead, 2)
    grand = round(line_total + op_total + tax_total, 2)

    story = []
    # ---- cover
    lab = St("lab", alignment=TA_RIGHT)
    val = St("val")

    def info(rows):
        data = [[Paragraph(f"{a}" if a else "", lab), Paragraph(esc(b), val),
                 Paragraph(f"{c}" if c else "", lab), Paragraph(esc(e), val)] for a, b, c, e in rows]
        t = Table(data, colWidths=[1.55 * inch, 3.2 * inch, 1.3 * inch, 2.05 * inch])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    # "805 29th St, Unit 111, Boulder, CO 80303" -> street line + city line
    addr = d.get("address", "")
    a1, a2 = addr, ""
    parts = [p.strip() for p in addr.split(",")]
    if len(parts) >= 3:
        a1, a2 = ", ".join(parts[:-2]), f"{parts[-2]}, {parts[-1]}"
    story += [
        info([("Client:", d.get("customer", ""), "", ""), ("Property:", a1, "", ""), ("", a2, "", "")]),
        Spacer(1, 12),
        info([("Operator:", x.get("operator", ""), "", "")]),
        Spacer(1, 12),
        info([("Estimator:", x.get("estimator", ""), "Business:", x.get("business_phone", "")),
              ("Position:", x.get("position", ""), "E-mail:", x.get("email", "")),
              ("Company:", x.get("company", ""), "", "")]),
        Spacer(1, 12),
        info([("Type of Estimate:", d.get("type_of_estimate") or x.get("type_of_estimate", ""), "", ""),
              ("Date Entered:", date_s, "Date Assigned:", "")]),
        Spacer(1, 12),
        info([("Price List:", d.get("price_list") or x.get("price_list", ""), "", ""),
              ("Labor Efficiency:", x.get("labor_efficiency", ""), "", ""), ("Estimate:", est, "", "")]),
        Spacer(1, 14),
        Paragraph(f"<b>Total Estimate: {n2(grand)}</b>", P),
        Paragraph(x.get("deposit_html", ""), P),
    ]
    story += [Paragraph(t, P) for t in x.get("cover_paragraphs", [])]

    # ---- line items
    story += [PageBreak(), Paragraph(f"<b>{esc(est)}</b>", CENTER_B), Spacer(1, 4),
              Paragraph(f"<b>{esc(source)}</b>", CENTER_B), Spacer(1, 20)]
    n = 0
    recap_room = OrderedDict()          # (area, room) -> line total (no O&P)
    recap_cat = defaultdict(float)
    estimated = False

    def room_table(sec):
        nonlocal n, estimated
        items = sec.get("items", [])
        by_group = OrderedDict((g, []) for g in GROUP_ORDER)
        for i in items:
            by_group.setdefault(group_of(i), []).append(i)
        rows, styles = [head_row()], []
        tax = op = tot = 0.0
        for g, its in by_group.items():
            if not its:
                continue
            rows.append([Paragraph(f"<b><i>{esc(g)}</i></b>", GROUP), "", "", "", "", "", ""])
            styles.append(("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1)))
            for i in its:
                n += 1
                q, up = float(i.get("quantity", 0)), float(i.get("unit_price", 0))
                ext, iop, itax = job.ext(i), job.op(i), float(i.get("tax", 0) or 0)
                total = round(ext + iop + itax, 2)
                tax, op, tot = tax + itax, op + iop, tot + total
                recap_cat[category_of(i)] += ext
                star = " *" if i.get("price_source") == "estimated" else ""
                estimated |= bool(star)
                rem, rep = (up, 0.0) if removal(i["description"]) else (0.0, up)
                rows.append([Paragraph(f"{n}.&nbsp; {esc(i['description'])}{star}", CELL),
                             f"{q:,.2f} {i.get('unit', '')}", n2(rem), n2(rep), n2(itax), n2(iop), n2(total)])
                if i.get("note"):
                    rows.append([Paragraph(esc(i["note"]), NOTE), "", "", "", "", "", ""])
                    styles.append(("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1)))
        return rows, styles, tax, op, tot

    gc = [s for s in job.sections if "general conditions" in s["name"].lower()]
    room_secs = [s for s in job.sections if s not in gc]
    default_area = d.get("level") or x.get("default_level", "1st Floor")
    areas = OrderedDict()
    for s in room_secs:
        areas.setdefault(s.get("area") or default_area, []).append(s)

    def emit_section(sec, area_key):
        rows, styles, tax, op, tot = room_table(sec)
        title = sec["name"] + (f" (Optional: {sec['option']})" if sec.get("option") else "")
        r = rooms.get(sec["name"].lower())
        height = f"Height: {r['height_ft']:g}'" if r and r.get("height_ft") else ""
        head = [CondPageBreak(2.2 * inch), section_title(title, height)]
        if r:
            head += dims_block(r)
        head.append(Spacer(1, 8))
        story.append(KeepTogether(head))
        story.append(items_table(rows, styles))
        story.extend(total_line(f"Totals:  {sec['name']}", tax, op, tot))
        story.append(Spacer(1, 22))
        recap_room[(area_key, sec["name"])] = recap_room.get((area_key, sec["name"]), 0.0) + \
            sum(job.ext(i) for i in sec.get("items", []))
        return tax, op, tot

    src_tax = src_op = src_tot = 0.0
    for s in gc:
        t3 = emit_section(s, source)
        src_tax, src_op, src_tot = src_tax + t3[0], src_op + t3[1], src_tot + t3[2]
    for area, secs in areas.items():
        story += [CondPageBreak(2.5 * inch), Paragraph(f"<b>{esc(area)}</b>", CENTER_B), Spacer(1, 14)]
        a_tax = a_op = a_tot = 0.0
        for s in secs:
            t3 = emit_section(s, area)
            a_tax, a_op, a_tot = a_tax + t3[0], a_op + t3[1], a_tot + t3[2]
        story.extend(total_line(f"Total:  {area}", a_tax, a_op, a_tot, double=False))
        story.append(Spacer(1, 4))
        src_tax, src_op, src_tot = src_tax + a_tax, src_op + a_op, src_tot + a_tot
    story.extend(total_line(f"Total:  {source}", src_tax, src_op, src_tot, double=False))
    story += [Spacer(1, 8)]
    story.extend(total_line(f"Line Item Totals:  {est}", tax_total, op_total, grand, double=True))
    if estimated:
        story.append(Paragraph("* Not in Forefront's price history; price estimated - verify before sending.",
                               St("fl", fontName=FI, fontSize=8.5, spaceBefore=6)))

    # ---- Grand Total Areas
    rs = list(rooms.values())
    sm = lambda k, alt=None: sum(float(r.get(k) or (r.get(alt) if alt else 0) or 0) for r in rs)
    walls, floor = sm("wall_sf"), sm("floor_sf")
    ceil = sum(float(r.get("ceiling_sf") or r.get("floor_sf") or 0) for r in rs)
    fp = sm("floor_perimeter_lf")
    cp = sum(float(r.get("ceiling_perimeter_lf") or r.get("floor_perimeter_lf") or 0) for r in rs)
    ga = [[n2(walls), "SF Walls", n2(ceil), "SF Ceiling", n2(walls + ceil), "SF Walls and Ceiling"],
          [n2(floor), "SF Floor", n2(floor / 9), "SY Flooring", n2(fp), "LF Floor Perimeter"],
          ["0.00", "SF Long Wall", "0.00", "SF Short Wall", n2(cp), "LF Ceil. Perimeter"],
          [n2(floor), "Floor Area", n2(floor), "Total Area", n2(walls), "Interior Wall Area"]]
    t = Table(ga, colWidths=[0.95 * inch, 1.45 * inch, 0.85 * inch, 1.3 * inch, 0.9 * inch, 1.55 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), F, 9.5), ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                           ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("ALIGN", (4, 0), (4, -1), "RIGHT"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [PageBreak(), Paragraph("<b>Grand Total Areas:</b>", St("gta", fontName=FB)), Spacer(1, 4), t]

    # ---- Recap by Room
    pct = lambda v: f"{(v / line_total * 100 if line_total else 0):.2f}%"
    rows, st = [], [("FONT", (0, 0), (-1, -1), FB, 9.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    rows.append([f"Estimate: {est}", "", ""])
    rows.append(["", "", ""])
    rows.append([f"Area: {source}", "", ""])
    for (a, room), v in recap_room.items():
        if a == source:
            rows.append(["      " + room, n2(v), pct(v)])
    for area in areas:
        rows += [["", "", ""], [f"Area: {area}", "", ""]]
        sub = 0.0
        for (a, room), v in recap_room.items():
            if a == area:
                rows.append(["      " + room, n2(v), pct(v)])
                sub += v
        rows.append(["", "", ""])
        rows.append([f"      Area Subtotal:  {area}", n2(sub), pct(sub)])
        st += [("LINEABOVE", (0, len(rows) - 1), (0, len(rows) - 1), 0.6, colors.black),
               ("LINEABOVE", (1, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black)]
    rows.append(["", "", ""])
    rows.append([f"      Area Subtotal:  {source}", n2(line_total), pct(line_total)])
    st += [("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black)]
    rows += [["", "", ""], ["Subtotal of Areas", n2(line_total), "100.00%"]]
    st += [("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black),
           ("LINEBELOW", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black)]
    rows += [["", "", ""], ["Total", n2(line_total), "100.00%"]]
    t = Table(rows, colWidths=[4.6 * inch, 1.55 * inch, BODY_W - 6.15 * inch])
    t.setStyle(TableStyle(st))
    story += [PageBreak(), Paragraph("<b>Recap by Room</b>", CENTER_B14), Spacer(1, 16), t]

    # ---- Recap by Category
    gpct = lambda v: f"{(v / grand * 100 if grand else 0):.2f}%"
    rows = [["O&P Items", "Total", "%"]]
    for cat in sorted(recap_cat):
        rows.append([cat, n2(recap_cat[cat]), gpct(recap_cat[cat])])
    k = len(rows)
    rows += [["O&P Items Subtotal", n2(line_total), gpct(line_total)], ["Overhead", n2(overhead), gpct(overhead)],
             ["Profit", n2(profit), gpct(profit)]]
    if tax_total:
        rows.append(["Material Sales Tax", n2(tax_total), gpct(tax_total)])
    rows += [["Total", n2(grand), "100.00%"]]
    t = Table(rows, colWidths=[4.6 * inch, 1.55 * inch, BODY_W - 6.15 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), FB, 9.5), ("FONT", (0, 0), (-1, 0), FB, 11.5),
                           ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                           ("LINEABOVE", (0, k), (-1, k), 0.6, colors.black),
                           ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    story += [PageBreak(), Paragraph("<b>Recap by Category</b>", CENTER_B14), Spacer(1, 14), t, Spacer(1, 30)]
    if x.get("closing_html"):
        story.append(Paragraph(x["closing_html"], P))

    # ---- sketches (landscape)
    sketches = [s for s in d.get("sketches", []) if s.get("image") and Path(s["image"]).exists()]
    LW, LH = landscape(letter)

    def sketch_page(c, doc):
        c.saveState()
        pages.footer(c, doc, wide=True)
        c.restoreState()

    if sketches:
        story.append(NextPageTemplate("sketch"))
        for k, s in enumerate(sketches):
            story.append(PageBreak())
            story.append(SketchFlow(s, source, LW, LH))

    doc = BaseDocTemplate(str(path), pagesize=letter, title=est, author=x.get("estimator", ""))
    body = Frame(LM, BOTTOM, BODY_W, TOP - BOTTOM, id="body", leftPadding=0, rightPadding=0, topPadding=0,
                 bottomPadding=0)
    sk = Frame(0, 0, LW, LH, id="sk", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("portrait", [body], onPage=pages.portrait, pagesize=letter),
                          PageTemplate("sketch", [sk], onPage=sketch_page, pagesize=landscape(letter))])
    doc.build(story)
    return {"line_total": line_total, "overhead": overhead, "profit": profit, "total": grand}


class SketchFlow(Flowable):
    """A whole landscape page: area title top-left, floor plan centered, level name + north arrow bottom-right."""

    def __init__(self, sketch: dict, source: str, w: float, h: float):
        super().__init__()
        self.s, self.source, self.w, self.h = sketch, source, w, h

    def wrap(self, aw, ah):
        return aw, ah - 1

    def draw(self):
        c = self.canv
        title = self.s.get("title", "")
        c.setFont(F, 9.5)
        c.drawString(25, self.h - 30, f"{self.source} - {title}")
        img = ImageReader(self.s["image"])
        iw, ih = img.getSize()
        box_w, box_h = self.w - 200, self.h - 150
        sc = min(box_w / iw, box_h / ih)
        dw, dh = iw * sc, ih * sc
        c.drawImage(img, (self.w - dw) / 2, (self.h - dh) / 2 + 10, dw, dh, mask="auto")
        blue = colors.HexColor("#3d6e9e")
        c.setFillColor(blue)
        c.setFont(F, 15)
        c.drawRightString(self.w - 25, 52, title)
        c.setStrokeColor(blue)
        c.setLineWidth(1)
        ax = self.w - 50
        c.line(ax, 80, ax, 98)
        c.line(ax - 6, 92, ax, 99)
        c.line(ax + 6, 92, ax, 99)
        c.setFont(FB, 13)
        c.drawCentredString(ax, 104, "N")
