#!/usr/bin/env python3
"""Turn estimate.json into Forefront's documents (needs only reportlab, which Claude's sandbox has).

    python render.py estimate.json --out /mnt/user-data/outputs
    python render.py estimate.json --out out --only estimate          # estimate | agreement | xactimate

Writes:
    <Customer> - Reconstruction Estimate.pdf    trades with O&P-inclusive totals, bullets, exclusions, billing
    <Customer> - Reconstruction Agreement.pdf   same scope + material selections, waivers, terms, signature
    <Customer> - Xactimate style.pdf            room-by-room line items at price-book prices (no markup)

and prints the totals. The JSON format is in references/estimate_format.md.
Money math: O&P is figured per line (like Xactimate), markup is applied per trade on the customer
documents only, and the billing split rounds half-up with the last payment taking the remainder.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

NAVY = colors.HexColor("#16324a")
INK = colors.HexColor("#1f2933")
BODY = colors.HexColor("#3e4c59")
MUTED = colors.HexColor("#7b8794")
PALE = colors.HexColor("#eef2f6")
RULE = colors.HexColor("#c9d2dc")
SKY = colors.HexColor("#4a90c2")
LIGHT = colors.HexColor("#d5dde6")

TRADE_ORDER = ["Demolition & General Conditions", "Insulation", "Drywall", "Cabinetry & Vanities",
               "Plumbing / Shower", "Plumbing", "Electrical", "Flooring", "Finish Carpentry / Trim", "Appliances",
               "Painting", "Customer Selections"]

PAGE_W, PAGE_H = letter
MARGIN = 0.6 * inch
WIDTH = PAGE_W - 2 * MARGIN


def S(name, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=8, leading=11, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


BODY_S = S("body")
SMALL = S("small", fontSize=7.5, leading=10, textColor=MUTED)
LABEL = S("label", fontName="Helvetica-Bold", fontSize=6.5, leading=9)
H2 = S("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=12, spaceAfter=6)
H3 = S("h3", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=NAVY, spaceBefore=9, spaceAfter=2)
NOTE = S("note", fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=MUTED)
NOTE_BOX = S("notebox", fontSize=7.5, leading=10, textColor=BODY)
RIGHT = S("right", alignment=TA_RIGHT)


def esc(s) -> str:
    return escape(str(s or ""))


def r2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def money(v: float) -> str:
    return f"${v:,.2f}"


def payments(total: float, pcts: list[float]) -> list[float]:
    out = [r2(total * p / 100) for p in pcts[:-1]]
    return out + [r2(total - sum(out))]


# ---------------------------------------------------------------- data

class Job:
    def __init__(self, data: dict, company: dict):
        self.d = data
        self.c = company
        self.op_pct = float(data.get("overhead_pct", company.get("overhead_pct", 10))) + \
            float(data.get("profit_pct", company.get("profit_pct", 10)))
        mk = data.get("markup_pct")
        self.markup = float(company.get("markup_pct") or 0) if mk is None else float(mk)
        self.tax_pct = float(data.get("tax_pct", 0) or 0)
        self.sections = data.get("sections", [])
        self.options = list(dict.fromkeys(s.get("option", "") for s in self.sections if s.get("option")))
        when = data.get("date")
        self.date = date.fromisoformat(when) if when else date.today()

    # per-line money, like Xactimate
    @staticmethod
    def ext(i) -> float:
        return r2(float(i.get("quantity", 0)) * float(i.get("unit_price", 0)))

    def op(self, i) -> float:
        return r2(self.ext(i) * self.op_pct / 100)

    def line_total(self, i) -> float:
        return r2(self.ext(i) + float(i.get("tax", 0) or 0) + self.op(i))

    def items(self, option=None):
        for s in self.sections:
            if option is None or s.get("option", "") == option:
                for i in s.get("items", []):
                    yield s, i

    def xact_total(self, option="") -> float:
        items = [i for _, i in self.items(option)]
        return r2(sum(self.line_total(i) for i in items) + sum(self.ext(i) for i in items) * self.tax_pct / 100)

    def scopes(self) -> list[dict]:
        texts = {(t.get("option", ""), t["trade"]): t for t in self.d.get("trades", [])}
        scope_text = {s.get("option", ""): s for s in self.d.get("scopes", [])}
        out = []
        for option in ["", *self.options]:
            by_trade = defaultdict(list)
            for _, i in self.items(option):
                by_trade[i.get("trade") or "Demolition & General Conditions"].append(i)
            trades = []
            for trade in sorted(by_trade, key=trade_key):
                items = by_trade[trade]
                total = r2(sum(self.line_total(i) for i in items) * (1 + self.markup / 100))
                t = texts.get((option, trade), {})
                bullets = t.get("bullets") or list(dict.fromkeys(i["description"] for i in items))
                trades.append({"name": trade, "total": total, "bullets": bullets, "note": t.get("note", "")})
            st = scope_text.get(option, {})
            areas = st.get("areas") or ", ".join(dict.fromkeys(
                s["name"] for s in self.sections if s.get("option", "") == option
                and not any(w in s["name"].lower() for w in ("general conditions", "labor minimum"))))
            out.append({"option": option, "title": "Base Scope" if not option else f"Optional — {option}",
                        "total": r2(sum(t["total"] for t in trades)), "areas": areas,
                        "description": st.get("description", ""), "trades": trades})
        return out


def trade_key(t: str):
    base = t.split(" — ")[0]
    return (TRADE_ORDER.index(base) if base in TRADE_ORDER else len(TRADE_ORDER) - 1, t)


# ---------------------------------------------------------------- flowables

class Bar(Flowable):
    """Navy bar with a title on the left and an amount on the right."""

    def __init__(self, left: str, right: str = "", width=WIDTH, radius=3):
        super().__init__()
        self.left, self.right, self.width, self.height, self.radius = left, right, width, 18, radius

    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.roundRect(0, 0, self.width, self.height, self.radius, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(8, 5.5, self.left)
        if self.right:
            c.drawRightString(self.width - 8, 5.5, self.right)


class Bullet(Flowable):
    """A paragraph with a round bullet (estimate) or a short navy bar (agreement)."""

    def __init__(self, html: str, style=BODY_S, bar=False):
        super().__init__()
        self.p, self.bar = Paragraph(html, style), bar
        self.indent = 14 if bar else 11

    def wrap(self, aw, ah):
        w, h = self.p.wrap(aw - self.indent, ah)
        self.height = h + (3 if self.bar else 1)
        self.width = aw
        return aw, self.height

    def draw(self):
        top = self.height - (3 if self.bar else 1)
        if self.bar:
            self.canv.setFillColor(NAVY)
            self.canv.rect(2, top - 8, 1.8, 7, stroke=0, fill=1)
        else:
            self.canv.setFillColor(INK)
            self.canv.circle(5, top - 4.2, 1.1, stroke=0, fill=1)
        self.p.drawOn(self.canv, self.indent, top - self.p.height)


def rule(color=NAVY, width=1.5, space=6):
    t = Table([[""]], colWidths=[WIDTH], rowHeights=[1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), width, color), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, space)]


def callout(text: str, left_border=True):
    t = Table([[Paragraph(text, NOTE_BOX if not left_border else S("co", textColor=BODY))]], colWidths=[WIDTH])
    style = [("BACKGROUND", (0, 0), (-1, -1), PALE), ("LEFTPADDING", (0, 0), (-1, -1), 10),
             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
    if left_border:
        style.append(("LINEBEFORE", (0, 0), (0, -1), 4, NAVY))
    t.setStyle(TableStyle(style))
    return t


def money_table(rows, total_rows=(), italic_rows=(), plain_rows=(), col2=1.6 * inch):
    data = [[Paragraph(esc(a), BODY_S), Paragraph(f"<b>{esc(b)}</b>", RIGHT)] for a, b in rows]
    t = Table(data, colWidths=[WIDTH - col2, col2])
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for r in plain_rows:
        st.append(("LINEBELOW", (0, r), (-1, r), 0.6, RULE))
    for r in total_rows:
        data[r] = [Paragraph(f"<b>{esc(rows[r][0])}</b>", S("t", fontSize=9.5, leading=12)),
                   Paragraph(f"<b>{esc(rows[r][1])}</b>", S("tr", fontSize=9.5, leading=12, alignment=TA_RIGHT))]
        st += [("LINEABOVE", (0, r), (-1, r), 1.2, NAVY), ("LINEBELOW", (0, r), (-1, r), 1.2, NAVY)]
    for r in italic_rows:
        data[r] = [Paragraph(f"<i>{esc(rows[r][0])}</i>", S("i", textColor=BODY)),
                   Paragraph(f"<b><i>{esc(rows[r][1])}</i></b>", RIGHT)]
    t = Table(data, colWidths=[WIDTH - col2, col2])
    t.setStyle(TableStyle(st))
    return t


# ---------------------------------------------------------------- page furniture

def make_doc(path: Path, title: str, company: dict) -> BaseDocTemplate:
    band_h = 1.15 * inch
    logo = ASSETS / "logo.png"

    def first(c, doc):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 19)
        c.drawString(MARGIN, PAGE_H - 0.6 * inch, title)
        c.setFillColor(LIGHT)
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN, PAGE_H - 0.85 * inch, company.get("name", ""))
        if logo.exists():
            h = 0.42 * inch
            w = h * 800 / 123
            c.drawImage(str(logo), PAGE_W - MARGIN - w, PAGE_H - 0.78 * inch, w, h, mask="auto")
        c.restoreState()
        footer(c, doc)

    def footer(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#9aa5b1"))
        c.drawString(MARGIN, 0.4 * inch, title)
        c.drawRightString(PAGE_W - MARGIN, 0.4 * inch, f"{company.get('name', '')} | Page {doc.page}")
        c.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=letter, title=title, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=0.55 * inch, bottomMargin=0.65 * inch)
    f1 = Frame(MARGIN, 0.65 * inch, WIDTH, PAGE_H - band_h - 0.2 * inch - 0.65 * inch, id="f1",
               leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    f2 = Frame(MARGIN, 0.65 * inch, WIDTH, PAGE_H - 0.55 * inch - 0.65 * inch, id="f2",
               leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("first", [f1], onPage=first, autoNextPageTemplate="later"),
                          PageTemplate("later", [f2], onPage=footer)])
    return doc


def info_block(cols: list[tuple[str, str]], rule_color):
    cells = [[Paragraph(esc(lbl).upper(), LABEL) for lbl, _ in cols],
             [Paragraph(val, BODY_S) for _, val in cols]]
    t = Table(cells, colWidths=[WIDTH / len(cols)] * len(cols))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 1), (-1, 1), 10)]))
    return [t] + rule(rule_color, 1.2, 8)


def address_html(addr: str) -> str:
    street, _, rest = (addr or "").partition(", ")
    return esc(street) + (f"<br/>{esc(rest)}" if rest else "")


def scope_flowables(scope: dict, has_options: bool, agreement: bool) -> list:
    out = []
    if has_options:
        head = Table([[Paragraph(f"<b>{esc(scope['title'])}</b>", S("sh", fontSize=12, leading=15, textColor=NAVY)),
                       Paragraph(f"<b>{money(scope['total'])}</b>",
                                 S("shr", fontSize=12, leading=15, textColor=NAVY, alignment=TA_RIGHT))]],
                     colWidths=[WIDTH * 0.7, WIDTH * 0.3])
        head.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        out += [Spacer(1, 12), head]
        if scope["areas"]:
            out.append(Paragraph(esc(scope["areas"].rstrip(".")) + ".", S("areas", textColor=colors.HexColor("#5a6672"),
                                                                         spaceBefore=4, spaceAfter=4)))
        if scope["option"]:
            word = "Total Agreement Amount" if agreement else "Total Job Price"
            out.append(Paragraph(esc(scope["description"] or f"Optional add-on. Priced separately. This section is "
                                     f"not included in the {word} unless accepted."), NOTE))
    for t in scope["trades"]:
        block = [Spacer(1, 7), Bar(t["name"], money(t["total"])), Spacer(1, 3)]
        block += [Bullet(esc(b), bar=agreement) for b in t["bullets"]]
        if t["note"]:
            block += [Spacer(1, 3), callout(esc(t["note"]), left_border=not agreement) if len(t["note"]) > 130
                      else Paragraph(esc(t["note"]), NOTE)]
        out.append(KeepTogether(block))
    return out


def exclusions(company: dict, word: str, agreement: bool) -> list:
    out = [Paragraph("What This Does Not Include", H2)]
    for e in company.get("exclusions", []):
        out += [Bullet(f"<b>{esc(e['lead'])}</b> {esc(e['text'].replace('{doc}', word))}", bar=agreement), Spacer(1, 2)]
    return out


# ---------------------------------------------------------------- Reconstruction Estimate

def render_estimate(job: Job, company: dict, path: Path):
    d, scopes = job.d, job.scopes()
    has_options = len(scopes) > 1
    numbers = d.get("estimate_numbers") or ([d["estimate_number"]] if d.get("estimate_number") else [])
    job_lines = (f"Estimate: {esc(', '.join(numbers))}<br/>" if numbers else "") + \
        f"Estimator: {esc(d.get('estimator') or company.get('estimator', ''))}<br/>" \
        f"Date: {job.date.month}/{job.date.day}/{job.date.year}"
    story = info_block([("Property", address_html(d.get("address"))), ("Customer", esc(d.get("customer"))),
                        ("Job", job_lines)], NAVY)
    if d.get("intro"):
        story += [callout(esc(d["intro"])), Spacer(1, 6)]
    combined = r2(sum(s["total"] for s in scopes))
    names = " and ".join(s["option"] for s in scopes[1:])
    if has_options:
        rows = [("Base Scope", money(scopes[0]["total"])), ("Total Job Price (Base Scope)", money(scopes[0]["total"]))]
        rows += [(f"Optional: {s['option']}", money(s["total"])) for s in scopes[1:]]
        rows.append((f"Total Job Price with Optional {names}", money(combined)))
        story += [Paragraph("Cost Summary", H2),
                  money_table(rows, total_rows=[1, len(rows) - 1], italic_rows=range(2, len(rows) - 1),
                              plain_rows=[0, *range(2, len(rows) - 1)])]
    story.append(Paragraph(esc(company.get("amounts_note", "")), S("an", fontSize=7.5, textColor=MUTED, spaceBefore=6)))
    for scope in scopes:
        story += scope_flowables(scope, has_options, agreement=False)
    story += exclusions(company, "estimate", agreement=False)

    billing = company.get("billing", [])
    pcts = [b["pct"] for b in billing]
    tail = [Paragraph("Job Total &amp; Billing", H2)]
    if has_options:
        head = ["", "Total"] + [f"{b['short']} ({b['pct']:g}%)" for b in billing]
        rows = [("Total Job Price (Base Scope)", scopes[0]["total"], True)]
        rows += [(f"Optional: {s['option']}, if accepted", s["total"], False) for s in scopes[1:]]
        rows.append((f"Total Job Price with Optional {names}", combined, True))
        data = [[Paragraph(f"<b>{esc(h)}</b>", S("bh", fontSize=6.5, textColor=MUTED, alignment=TA_RIGHT)) for h in head]]
        for label, total, strong in rows:
            sz = 10 if strong else 7.5
            cell = S("bc", fontSize=sz, leading=sz + 3, alignment=TA_RIGHT, fontName="Helvetica-Bold" if strong else "Helvetica")
            data.append([Paragraph(esc(label), S("bl", fontSize=sz, leading=sz + 3, fontName="Helvetica-Bold" if strong else "Helvetica")),
                         Paragraph(money(total), S("bt", fontSize=sz, leading=sz + 3, fontName="Helvetica-Bold", alignment=TA_RIGHT))]
                        + [Paragraph(money(v), cell) for v in payments(total, pcts)])
        widths = [WIDTH * 0.34, WIDTH * 0.14] + [WIDTH * 0.52 / len(billing)] * len(billing)
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1.2, NAVY), ("LINEBELOW", (0, 1), (-1, -2), 0.6, RULE),
                               ("LINEBELOW", (0, -1), (-1, -1), 1.2, NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 1), (-1, -1), 7), ("BOTTOMPADDING", (0, 1), (-1, -1), 7)]))
        tail += [t, Paragraph(f"Payment for the Base Scope, and for the optional {esc(names.lower())} if accepted, is "
                              "Owner’s responsibility per the schedule above.", S("p", fontSize=7.5, textColor=MUTED, spaceBefore=6))]
    else:
        total = scopes[0]["total"]
        rows = [("Total Job Price", money(total))] + [(f"{b['label']} ({b['pct']:g}%)", money(v))
                                                     for b, v in zip(billing, payments(total, pcts))]
        tail += [money_table(rows, total_rows=[0], plain_rows=range(1, len(rows))),
                 Paragraph("Payment for the full Total Job Price is Owner’s responsibility per the schedule above.",
                           S("p", fontSize=7.5, textColor=MUTED, spaceBefore=6))]
    tail += [Spacer(1, 6), Paragraph(esc(company.get("license_line", "")), BODY_S)]
    story.append(KeepTogether(tail))
    make_doc(path, "Reconstruction Estimate", company).build(story)
    return scopes


# ---------------------------------------------------------------- Reconstruction Agreement

def render_agreement(job: Job, company: dict, path: Path):
    d, scopes = job.d, job.scopes()
    has_options = len(scopes) > 1
    story = info_block([("Property", address_html(d.get("address"))), ("Customer", esc(d.get("customer")))], SKY)
    if d.get("intro"):
        story += [callout(esc(d["intro"])), Spacer(1, 6)]
    for scope in scopes:
        story += scope_flowables(scope, has_options, agreement=True)

    sels = d.get("selections") or []
    if sels:
        story += [PageBreak(), Paragraph("Material Selections", H2)] + rule(SKY, 0.8, 6)
        for sel in sels:
            fields = [tuple(f) if isinstance(f, (list, tuple)) else (f["label"], f["value"]) for f in sel.get("fields", [])]
            fields.append(("Viewed", sel.get("viewed", "Online only (not viewed in person)")))
            rows = [[Paragraph(f"<b>{esc(k).upper()}</b>", S("k", fontSize=6.5, textColor=MUTED)), Paragraph(esc(v), BODY_S)]
                    for k, v in fields]
            tbl = Table(rows, colWidths=[1.3 * inch, WIDTH - 1.3 * inch - 1.75 * inch])
            tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEBELOW", (0, 0), (-1, -1), 2, colors.white),
                                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            img_cell = ""
            img = sel.get("image")
            if img and Path(img).exists():
                img_cell = [Image(img, width=1.6 * inch, height=1.6 * inch, kind="proportional"),
                            Paragraph(esc(sel.get("caption", "")), S("cap", fontSize=6.5, textColor=MUTED))]
            row = Table([[tbl, img_cell]], colWidths=[WIDTH - 1.75 * inch, 1.75 * inch])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(KeepTogether([Bar(sel.get("title", ""), radius=0), row, Spacer(1, 10)]))
        story.append(Paragraph("SELECTION ACKNOWLEDGMENTS", H3))
        for a in company.get("selection_acknowledgments", []):
            story.append(Bullet(f"<b>{esc(a['lead'])}</b> {esc(a['text'])}", bar=True))

    story += exclusions(company, "agreement", agreement=True)
    rows = [("Scope of work" if not s["option"] else f"Optional: {s['option']}", money(s["total"])) for s in scopes]
    total = scopes[0]["total"]
    rows.append(("Total Agreement Amount", money(total)))
    pcts = [b["pct"] for b in company.get("billing", [])]
    bill = [(f"{b['label']} ({b['pct']:g}%)", money(v)) for b, v in zip(company.get("billing", []), payments(total, pcts))]
    story.append(KeepTogether([Spacer(1, 8), money_table(rows, total_rows=[len(rows) - 1], plain_rows=range(len(rows) - 1)),
                               Paragraph("Billing", H2), money_table(bill, plain_rows=range(len(bill)))]))

    story += [PageBreak(), Paragraph("Waivers and Acknowledgments", H2)] + rule(SKY, 0.8, 4)
    for w in company.get("waivers", []):
        story.append(KeepTogether([Paragraph(esc(w["heading"]).upper(), H3)] + [Bullet(esc(i), bar=True) for i in w["items"]]))
    story += [Paragraph("Reconstruction Work Authorization / Direct to Pay", H2)] + rule(SKY, 0.8, 4)
    story.append(Paragraph(esc(company.get("agreement_terms_intro", "")), BODY_S))
    for n, t in enumerate(company.get("agreement_terms", []), 1):
        story.append(Paragraph(f"{n}. {esc(t['text'])}", S("term", leftIndent=12, firstLineIndent=-12, spaceBefore=3)))
        for letter_, sub in zip("abcdefghij", t.get("sub", [])):
            story.append(Paragraph(f"{letter_}. {esc(sub)}", S("sub", leftIndent=26, firstLineIndent=-10, spaceBefore=1)))
    story += [Spacer(1, 6), Paragraph(f"<b>{esc(company.get('agreement_terms_footer', ''))}</b>", BODY_S), Spacer(1, 4),
              Paragraph(esc(company.get("license_line", "")), BODY_S)]
    sign = Table([[Paragraph("<b>CUSTOMER SIGNATURE / DATE</b>", S("sg", fontSize=6.5))]], colWidths=[WIDTH * 0.55])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.8, INK), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([Paragraph("Approval", H2), Paragraph(esc(company.get("approval_text", "")), BODY_S),
                               Spacer(1, 36), sign]))
    make_doc(path, "Reconstruction Agreement", company).build(story)


# ---------------------------------------------------------------- Xactimate-style PDF

def render_xactimate(job: Job, company: dict, path: Path):
    d = job.d
    rooms = {r["name"].lower(): r for r in d.get("rooms", []) if r.get("name")}
    small = S("xs", fontSize=8, leading=10)
    cols = [3.35 * inch, 0.95 * inch, 0.75 * inch, 0.6 * inch, 0.7 * inch, 0.85 * inch]
    head = Table([[Paragraph(f"<b>{esc(company.get('legal_name') or company.get('name'))}</b><br/>{esc(company.get('address'))}"
                             f"<br/>{esc(company.get('phone'))}", small),
                   Paragraph(f"<b>Insured:</b> {esc(d.get('customer'))}<br/><b>Property:</b> {esc(d.get('address'))}<br/>"
                             f"<b>Claim Number:</b> {esc(d.get('claim_number'))}<br/><b>Date:</b> {job.date:%m/%d/%Y}<br/>"
                             f"<b>Estimate:</b> {esc(d.get('estimate_number'))}", small)]],
                 colWidths=[3.6 * inch, 3.7 * inch])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black)]))
    story = [head, Spacer(1, 6)]
    n, recap = 0, defaultdict(float)
    grand = {"tax": 0.0, "op": 0.0, "rcv": 0.0}
    for s in job.sections:
        rows = [["DESCRIPTION", "QUANTITY", "UNIT PRICE", "TAX", "O&P", "RCV"]]
        spans, sub = [], {"tax": 0.0, "op": 0.0, "rcv": 0.0}
        for i in s.get("items", []):
            n += 1
            ext, op, tax = job.ext(i), job.op(i), float(i.get("tax", 0) or 0)
            rcv = r2(ext + tax + op)
            for k, v in (("tax", tax), ("op", op), ("rcv", rcv)):
                sub[k] += v
            recap[i.get("trade") or "Other"] += ext
            flag = " *" if i.get("price_source") == "estimated" else ""
            rows.append([Paragraph(f"{n}. {esc(i['description'])}{flag}", small), f"{float(i.get('quantity', 0)):,.2f} {i.get('unit', '')}",
                         f"{float(i.get('unit_price', 0)):,.2f}", f"{tax:,.2f}", f"{op:,.2f}", f"{rcv:,.2f}"])
            if i.get("note"):
                rows.append([Paragraph(esc(i["note"]), S("xn", fontSize=7, leading=9, textColor=MUTED, leftIndent=14)), "", "", "", "", ""])
                spans.append(("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1)))
        rows.append([Paragraph(f"<b>Totals: {esc(s['name'])}</b>", small), "", "", f"{sub['tax']:,.2f}", f"{sub['op']:,.2f}", f"{sub['rcv']:,.2f}"])
        for k in grand:
            grand[k] += sub[k]
        t = Table(rows, colWidths=cols, repeatRows=1)
        t.setStyle(TableStyle(spans + [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8), ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        r = rooms.get(s["name"].lower())
        title = s["name"] + (f" (Optional: {s['option']})" if s.get("option") else "")
        dims = ""
        if r:
            bits = [f"Height: {r['height_ft']:g}'" if r.get("height_ft") else ""] + [
                f"{r[k]:,.2f} {lbl}" for k, lbl in (("wall_sf", "SF Walls"), ("floor_sf", "SF Floor"),
                                                    ("floor_perimeter_lf", "LF Floor Perimeter"), ("perimeter_lf", "LF Floor Perimeter"))
                if r.get(k)]
            dims = " &nbsp; ".join(b for b in dict.fromkeys(bits) if b)
        story.append(KeepTogether([Paragraph(f"<b>{esc(title)}</b>", S("rm", fontSize=10, leading=13, spaceBefore=10))]
                                  + ([Paragraph(dims, small)] if dims else []) + [Spacer(1, 3)]))
        story.append(t)
    line_total = r2(sum(job.ext(i) for _, i in job.items()))
    t = Table([["Line Item Totals", "", "", f"{grand['tax']:,.2f}", f"{grand['op']:,.2f}", f"{grand['rcv']:,.2f}"]], colWidths=cols)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                           ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black)]))
    story += [Spacer(1, 8), t, Paragraph("<b>Recap by Trade</b>", S("rh", fontSize=10, spaceBefore=12, spaceAfter=4))]
    rec = [["Trade", "Amount", "%"]] + [[k, f"{v:,.2f}", f"{(v / line_total * 100 if line_total else 0):.2f}%"]
                                       for k, v in sorted(recap.items(), key=lambda kv: trade_key(kv[0]))]
    t = Table(rec, colWidths=[3 * inch, 1.2 * inch, 0.8 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    story.append(t)
    summ = [["Line Item Total", f"{line_total:,.2f}"], ["Overhead & Profit", f"{grand['op']:,.2f}"],
            ["Sales Tax", f"{grand['tax']:,.2f}"], ["Replacement Cost Value (all sections)", f"{grand['rcv']:,.2f}"]]
    t = Table(summ, colWidths=[3 * inch, 1.5 * inch])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
                           ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]))
    story += [Paragraph("<b>Summary</b>", S("sh2", fontSize=10, spaceBefore=12, spaceAfter=4)), t]
    if any(i.get("price_source") == "estimated" for _, i in job.items()):
        story.append(Paragraph("* Not in the price book - price estimated; check before sending.",
                               S("fl", fontSize=7, textColor=MUTED, spaceBefore=6)))

    def page(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.drawString(MARGIN, 0.45 * inch, f"{d.get('estimate_number', '')}  {job.date:%m/%d/%Y}")
        c.drawRightString(PAGE_W - MARGIN, 0.45 * inch, f"Page: {doc.page}")
        c.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=0.6 * inch,
                          bottomMargin=0.7 * inch, title=d.get("estimate_number", "Estimate"))
    doc.addPageTemplates([PageTemplate("all", [Frame(MARGIN, 0.7 * inch, WIDTH, PAGE_H - 1.3 * inch, id="x",
                                                     leftPadding=0, rightPadding=0)], onPage=page)])
    doc.build(story)


# ---------------------------------------------------------------- main

def safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in " -_.,&" else "_" for ch in name).strip() or "Estimate"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("estimate", type=Path)
    p.add_argument("--out", type=Path, default=Path("."))
    p.add_argument("--only", default="estimate,agreement,xactimate")
    p.add_argument("--company", type=Path, default=ASSETS / "company.json")
    a = p.parse_args(argv)

    data = json.loads(a.estimate.read_text(encoding="utf-8"))
    company = json.loads(a.company.read_text(encoding="utf-8"))
    job = Job(data, company)
    problems = [f"{s['name']}: '{i.get('description', '?')}' has no trade" for s, i in job.items() if not i.get("trade")]
    for msg in problems[:10]:
        print("! " + msg, file=sys.stderr)

    a.out.mkdir(parents=True, exist_ok=True)
    stem = safe(data.get("customer") or data.get("estimate_number") or "Estimate")
    wanted = {w.strip() for w in a.only.split(",")}
    written = []
    if "estimate" in wanted:
        written.append(a.out / f"{stem} - Reconstruction Estimate.pdf")
        render_estimate(job, company, written[-1])
    if "agreement" in wanted:
        written.append(a.out / f"{stem} - Reconstruction Agreement.pdf")
        render_agreement(job, company, written[-1])
    if "xactimate" in wanted:
        written.append(a.out / f"{stem} - Xactimate style.pdf")
        render_xactimate(job, company, written[-1])

    scopes = job.scopes()
    print(f"Markup on customer documents: {job.markup:g}%   O&P: {job.op_pct:g}%")
    for s in scopes:
        print(f"{s['title']}: {money(s['total'])}  (Xactimate-style, no markup: {money(job.xact_total(s['option']))})")
        for t in s["trades"]:
            print(f"    {t['name']:<34} {money(t['total']):>12}")
    est = [i["description"] for _, i in job.items() if i.get("price_source") == "estimated"]
    if est:
        print(f"{len(est)} items priced without price-book history: " + "; ".join(est[:12]))
    for f in written:
        print(f"-> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
