"""Offline reader for Xactimate estimate PDFs (no AI, no cost).

Uses the fonts and spacing Xactimate prints with:
  * line items   - regular text starting "12. " and ending in the number columns
  * wrapped text - regular text sitting tight (~10pt) under an item line
  * item notes   - regular text further below an item
  * trade groups - bold-italic headings ("Drywall", "Cabinets & Sink")
  * rooms        - each room ends with "Totals: <Room> tax o&p total"; dimensions come from
                   the bold "<Room> Height: 7' 9"" block and the SF/LF lines under it.

Every room total is checked against the printed "Totals:" line, so you know the import is exact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from ..models import Estimate, LineItem, Room, Section

UNITS = r"SF|LF|SY|EA|HR|CF|CY|SQ|DA|WK|MO|GL|LS|RM|BX|PR|TN|RL|DY|MH|RN|KT|ST|BG|LB|PK|CS|SH|PC|TH"
MONEY = r"\(?-?[\d,]+\.\d{2}\)?"
ITEM_RE = re.compile(rf"^(?P<n>\d+)\.\s+(?P<desc>.*?)\s*(?P<qty>-?[\d,]+\.\d{{2}})\s*(?P<unit>{UNITS})\s+(?P<nums>(?:{MONEY}\s*){{4,6}})$")
TOTALS_RE = re.compile(rf"^Totals:\s+(?P<name>.+?)\s+(?P<tax>{MONEY})\s+(?P<op>{MONEY})\s+(?P<total>{MONEY})$")
GRAND_RE = re.compile(rf"^Line Item Totals:\s+.+?\s+(?P<tax>{MONEY})\s+(?P<op>{MONEY})\s+(?P<total>{MONEY})$")
DIM_PATTERNS = {
    "wall_sf": r"([\d,]+\.\d+)\s*SF Walls(?! &)",
    "ceiling_sf": r"([\d,]+\.\d+)\s*SF Ceiling",
    "floor_sf": r"([\d,]+\.\d+)\s*SF Floor",
    "perimeter_lf": r"([\d,]+\.\d+)\s*LF Floor Perimeter",
}
TIGHT = 12.5  # max gap (pt) between an item line and its wrapped continuation
NOTE_GAP = 22  # max gap between lines of the same note


def money(s: str) -> float:
    s = s.replace(",", "")
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-"))
    return -v if neg else v


def feet(s: str) -> float | None:
    m = re.match(r"\s*(\d+)'\s*(?:(\d+)(?:\s+(\d+)/(\d+))?\")?", s)
    if not m:
        return None
    inches = float(m[2] or 0) + (float(m[3]) / float(m[4]) if m[3] else 0)
    return round(int(m[1]) + inches / 12, 2)


@dataclass
class Line:
    text: str
    top: float
    font: str
    size: float

    @property
    def regular(self) -> bool:
        return "Bold" not in self.font and "Italic" not in self.font

    @property
    def group(self) -> bool:
        return "BoldItalic" in self.font or ("Bold" in self.font and "Italic" in self.font)

    @property
    def bold(self) -> bool:
        return "Bold" in self.font and not self.group


@dataclass
class ParseResult:
    estimate: Estimate
    checks: list[tuple[str, float, float]] = field(default_factory=list)  # (section, parsed, printed)
    printed_total: float | None = None

    @property
    def ok(self) -> bool:
        return all(abs(a - b) < 0.02 for _, a, b in self.checks) and bool(self.checks)

    def report(self) -> str:
        bad = [f"{n}: parsed {a:,.2f} vs printed {b:,.2f}" for n, a, b in self.checks if abs(a - b) >= 0.02]
        return "all room totals match" if self.ok else ("; ".join(bad) or "no room totals found")


def _lines(pdf) -> list[list[Line]]:
    pages = []
    for page in pdf.pages:
        out = []
        for l in page.extract_text_lines():
            chars = [c for c in l["chars"] if c["text"].strip()]
            if not chars:
                continue
            fonts: dict[tuple[str, float], int] = {}
            for c in chars:
                k = (c["fontname"].split("+")[-1], round(c["size"], 1))
                fonts[k] = fonts.get(k, 0) + 1
            font, size = max(fonts, key=fonts.get)
            out.append(Line(l["text"].strip(), l["top"], font, size))
        pages.append(out)
    return pages


def _room_name(text: str) -> str:
    name = text.split("Height:")[0].replace("Subroom:", "")
    tokens = [t for t in name.split() if not re.search(r"\d['\"]|['\"]\d|^\d+['\"]?$", t)]
    return " ".join(tokens).strip()


def parse_xactimate(path: Path) -> ParseResult:
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        pages = _lines(pdf)
    flat_text = "\n".join(l.text for p in pages for l in p)

    est = Estimate(source_file=path.name, title=path.stem)
    _header(flat_text, est)

    rooms: dict[str, Room] = {}
    pending: list[LineItem] = []
    checks: list[tuple[str, float, float]] = []
    printed_total = None
    item_totals: dict[int, float] = {}  # id(item) -> printed line total incl. O&P
    group = ""

    for lines in pages:
        in_table = False
        last_kind, last_top = "", 0.0
        dim_room: Room | None = None
        for ln in lines:
            t = ln.text
            if ln.bold and "Height:" in t:
                in_table = False
                if t.startswith("Subroom:"):
                    dim_room = None
                    continue
                dim_room = Room(name=_room_name(t), height_ft=feet(t.split("Height:")[1]))
                rooms[dim_room.name.lower()] = dim_room
                continue
            if dim_room is not None and ln.regular and ln.size >= 9.5:
                for key, pat in DIM_PATTERNS.items():
                    m = re.search(pat, t)
                    if m and getattr(dim_room, key) is None:
                        setattr(dim_room, key, float(m[1].replace(",", "")))
                continue
            if t.startswith("DESCRIPTION") and "QTY" in t:
                in_table, dim_room = True, None
                last_kind = "header"
                continue
            if m := GRAND_RE.match(t):
                printed_total = money(m["total"])
                continue
            if m := TOTALS_RE.match(t):
                name = m["name"].strip()
                parsed = round(sum(item_totals.get(id(i), 0.0) for i in pending), 2)
                checks.append((name, parsed, money(m["total"])))
                est.sections.append(Section(name=name, room=rooms.get(name.lower()), items=pending))
                pending, group, in_table, last_kind = [], "", False, "totals"
                continue
            if not in_table:
                continue
            if ln.group:
                group, last_kind = t, "group"
            elif ln.regular and (m := ITEM_RE.match(t)):
                nums = [money(x) for x in re.findall(MONEY, m["nums"])]
                *prices, tax, op, total = nums
                item = LineItem(description=m["desc"].strip(), quantity=money(m["qty"]), unit=m["unit"],
                                unit_price=round(sum(prices), 2), tax=tax, group=group, price_source="history")
                item_totals[id(item)] = total
                pending.append(item)
                last_kind = "item"
            elif ln.regular and pending:
                gap = ln.top - last_top
                if last_kind in ("item", "cont") and gap <= TIGHT:
                    pending[-1].description += " " + t
                    last_kind = "cont"
                elif last_kind in ("item", "cont", "note") and gap <= NOTE_GAP:
                    pending[-1].note = (pending[-1].note + "\n" + t).strip()
                    last_kind = "note"
                else:
                    last_kind = "other"
            last_top = ln.top

    if est.sections:
        n_items = sum(len(s.items) for s in est.sections)
        est.summary = est.summary or f"{n_items} line items across {', '.join(s.name for s in est.sections)}."
    return ParseResult(est, checks, printed_total)


def _header(text: str, est: Estimate) -> None:
    def grab(label: str) -> str:
        m = re.search(rf"^{label}:\s*(.+)$", text, re.M)
        return m[1].strip() if m else ""

    est.customer = grab("Client")
    prop = re.search(r"^Property:\s*(.+)\n(.+)$", text, re.M)
    if prop:
        est.address = f"{prop[1].strip()}, {prop[2].strip()}"
    est.claim_number = grab("Claim Number")
    est.loss_type = grab("Type of Loss")
    name = grab("Estimate")
    if name:
        est.title = name
    est.price_list = grab("Price List")
    m = re.search(r"Overhead \((\d+(?:\.\d+)?)%\)\s+Profit \((\d+(?:\.\d+)?)%\)", text)
    if m:
        est.overhead_pct, est.profit_pct = float(m[1]), float(m[2])


def is_xactimate(path: Path) -> bool:
    with pdfplumber.open(path) as pdf:
        head = "\n".join((p.extract_text() or "") for p in pdf.pages[:4])
    return bool(re.search(r"^DESCRIPTION\s+QTY\b", head, re.M)) or "Xactimate" in head
