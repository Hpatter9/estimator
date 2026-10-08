"""Read a past estimate PDF of any layout with Claude.

Xactimate PDFs don't need this - xactimate_pdf.py reads them offline. This is the fallback for
other layouts, or an Xactimate PDF whose room totals didn't check out.
"""
from __future__ import annotations

from pathlib import Path

from .. import ai
from ..models import Estimate

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
