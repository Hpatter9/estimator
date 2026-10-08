"""Read past estimates out of PDFs (Xactimate exports or your own template).

Two paths:
  * ai_extract_estimate - sends the PDF to Claude; works on any layout (recommended)
  * parse_estimate_pdf  - offline regex parser tuned for Xactimate-style line items
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .. import ai
from ..models import Estimate, LineItem, Section

UNITS = "SF|LF|SY|EA|HR|CF|CY|SQ|DA|WK|MO|GL|LS|RM|BX|PR|TN|RL|DY"
NUM = r"\(?-?[\d,]+\.\d{2}\)?"
LINE_RE = re.compile(
    rf"^(?:\d+\.\s+)?(?P<desc>.+?)\s+(?P<qty>[\d,]+\.\d{{2}})\s*(?P<unit>{UNITS})\s+(?P<nums>(?:{NUM}\s*)+)$"
)


def _num(s: str) -> float:
    s = s.replace(",", "")
    neg = s.startswith("(")
    v = float(s.strip("()"))
    return -v if neg else v


def pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parse_estimate_text(text: str, title: str = "") -> Estimate:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    split_remove_replace = bool(re.search(r"\bREMOVE\b.*\bREPLACE\b", text))
    sections: list[Section] = []
    current: Section | None = None
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if re.match(r"^(Height|Ceiling Height)\b", nxt) or re.search(r"SF Walls", nxt):
            if not LINE_RE.match(line) and not re.match(r"^(Height|Ceiling Height)\b", line):
                current = Section(name=line)
                sections.append(current)
                continue
        m = LINE_RE.match(line)
        if not m:
            continue
        nums = [_num(n) for n in re.findall(NUM, m["nums"])]
        if split_remove_replace and len(nums) >= 2:
            unit_price, tax = nums[0] + nums[1], (nums[2] if len(nums) > 2 else 0.0)
        else:
            unit_price, tax = nums[0], (nums[1] if len(nums) > 1 else 0.0)
        if current is None:
            current = Section(name="General")
            sections.append(current)
        current.items.append(LineItem(
            description=m["desc"].strip(), quantity=_num(m["qty"]), unit=m["unit"],
            unit_price=unit_price, tax=tax, price_source="history",
        ))
    return Estimate(title=title, sections=[s for s in sections if s.items])


def parse_estimate_pdf(path: Path) -> Estimate:
    est = parse_estimate_text(pdf_text(path), title=Path(path).stem)
    est.source_file = Path(path).name
    return est


EXTRACT_SCHEMA = ai.obj({
    "title": ai.STR, "customer": ai.STR, "address": ai.STR, "claim_number": ai.STR,
    "loss_type": ai.STR, "summary": ai.STR,
    "overhead_pct": ai.NUM, "profit_pct": ai.NUM, "tax_pct": ai.NUM,
    "sections": {"type": "array", "items": ai.obj({
        "name": ai.STR,
        "room": {"anyOf": [ai.ROOM_SCHEMA, {"type": "null"}]},
        "items": {"type": "array", "items": ai.LINE_ITEM_SCHEMA},
    })},
})

EXTRACT_SYSTEM = """You convert construction / restoration estimates (usually Xactimate exports) into JSON.
Rules:
- Copy every line item exactly once, in order, grouped by the room/area heading it appears under.
- unit_price is the full per-unit price. If the estimate splits REMOVE and REPLACE columns, add them together.
- category/selector: use the Xactimate category code and selector if printed (e.g. DRY, 1/2); otherwise
  infer the most likely Xactimate category code and leave selector empty.
- Include room dimensions when the estimate prints them (wall SF, floor SF, perimeter, height).
- summary: 2-4 sentences describing the job scope (loss type, rooms affected, main work), written so it
  can be matched against future job notes.
- Percentages are numbers like 10 for 10%. Use 0 when not shown. Use "" for unknown text fields."""


def ai_extract_estimate(path: Path) -> Estimate:
    data = ai.structured(EXTRACT_SYSTEM, [ai.file_block(Path(path)), {"type": "text", "text": "Convert this estimate."}],
                         EXTRACT_SCHEMA, effort="medium")
    for s in data["sections"]:
        for it in s["items"]:
            it["price_source"] = "history"
    est = Estimate.model_validate(data)
    est.source_file = Path(path).name
    return est
