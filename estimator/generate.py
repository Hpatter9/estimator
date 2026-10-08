"""Draft a new estimate from job notes + DocuSketch rooms, using your past estimates as the playbook.

How it works:
  1. Find the past jobs most similar to these notes (full-text search in the library).
  2. Build your price book - every line item you've used, with the prices you charged.
  3. Claude writes the scope: which line items, in which rooms, with quantities taken from the
     measurements, following how *you* scoped similar jobs.
  4. Prices are then filled from your history wherever the item matches; anything Claude had to
     price itself is marked price_source="ai" so you know to check it.
"""
from __future__ import annotations

from pathlib import Path

from . import ai
from .library import Library, PriceEntry
from .models import Estimate, LineItem, Room, Section
from .trades import fill_missing_trades

GEN_ITEM_SCHEMA = ai.obj({
    "category": ai.STR, "selector": ai.STR, "description": ai.STR,
    "quantity": ai.NUM, "unit": ai.STR,
    "price_book_match": ai.STR,
    "suggested_unit_price": ai.NUM,
    "note": ai.STR,
})

GEN_SCHEMA = ai.obj({
    "title": ai.STR, "loss_type": ai.STR, "summary": ai.STR,
    "sections": {"type": "array", "items": ai.obj({
        "name": ai.STR,
        "option": ai.STR,
        "items": {"type": "array", "items": GEN_ITEM_SCHEMA},
    })},
    "questions": {"type": "array", "items": ai.STR},
})

SYSTEM = """You are an experienced restoration / construction estimator writing a new estimate for the user's company.
The user's past estimates and price book are your playbook: scope the job the way they scope similar jobs,
use their line-item wording, and prefer items from their price book.

Rules:
- One section per room/area from the measurements (plus "General" for job-wide items like equipment, dumpster, permits).
- Quantities come from the room measurements: e.g. drywall/paint on walls -> wall SF, flooring -> floor SF,
  baseboard -> perimeter LF, ceilings -> ceiling SF. Apply cut heights from the notes (e.g. 2 ft flood cut ->
  perimeter LF x 2 SF). Round sensibly, the way the past estimates do.
- price_book_match: copy the exact description of the price-book item you are using, or "" if none fits.
- suggested_unit_price: your best per-unit price for the area/market implied by past estimates. It is only
  used when price_book_match is "".
- note: brief justification when the quantity isn't obvious (e.g. "2ft flood cut x 46 LF").
- Don't invent damage that isn't in the notes, photos or measurements. If something important is unclear,
  scope the most likely option and add a question to `questions`.
- option: "" for the base scope. Only when the notes say an area or piece of work is optional / priced
  separately / an add-on, put it in its own section(s) with option set to a short name like "Pantry Repairs".
- Write line-item descriptions in Xactimate wording, like the past estimates. Put a short line-item note where
  the past estimates would (why an item is needed, how a quantity was figured).
- summary: 2-4 sentences describing the scope."""


def _fmt_room(r: Room) -> str:
    vals = {k: v for k, v in r.model_dump().items() if v not in (None, "") and k != "name"}
    return f"- {r.name}: " + ", ".join(f"{k}={v}" for k, v in vals.items())


def _fmt_estimate(e: Estimate) -> str:
    out = [f"### {e.title or e.source_file} ({e.loss_type})", e.summary]
    for s in e.sections:
        out.append(f"[{s.name}]")
        out += [f"  {i.category} {i.selector} | {i.description} | {i.quantity:g} {i.unit} @ {i.unit_price:.2f}"
                for i in s.items]
    return "\n".join(out)


def _fmt_price_book(book: list[PriceEntry], limit: int = 600) -> str:
    rows = ["category | selector | description | unit | median price | (min-max) | times used"]
    rows += [f"{p.category} | {p.selector} | {p.description} | {p.unit} | {p.median_price:.2f} | "
             f"({p.min_price:.2f}-{p.max_price:.2f}) | {p.times_used}" for p in book[:limit]]
    return "\n".join(rows)


def generate_estimate(
    library: Library,
    notes: str,
    rooms: list[Room],
    photos: list[Path] = (),
    extra_files: list[Path] = (),
    customer: str = "",
    address: str = "",
    claim_number: str = "",
    overhead_pct: float = 10.0,
    profit_pct: float = 10.0,
    tax_pct: float = 0.0,
    n_similar: int = 3,
    customer_scope: bool = True,
) -> tuple[Estimate, list[str]]:
    """Returns (estimate, open questions for you)."""
    room_names = " ".join(r.name for r in rooms)
    similar = library.similar(f"{notes} {room_names}", limit=n_similar)
    book = library.price_book()

    # Stable reference material first (cacheable), job-specific material last.
    content: list[dict] = [
        {"type": "text", "text": "## Your price book (from past estimates)\n" + (_fmt_price_book(book) if book else "(empty)")},
        {"type": "text", "text": "## Most similar past estimates\n" + ("\n\n".join(_fmt_estimate(e) for e in similar) or "(none yet)"),
         "cache_control": {"type": "ephemeral"}},
    ]
    for f in [*extra_files, *photos]:
        content.append(ai.file_block(Path(f)))
    content.append({"type": "text", "text": (
        "## New job\n"
        f"Customer: {customer}\nAddress: {address}\n\n"
        "### Room measurements (DocuSketch)\n" + ("\n".join(_fmt_room(r) for r in rooms) or "(none provided)") +
        "\n\n### Notes\n" + notes.strip() +
        "\n\nWrite the estimate."
    )})

    data = ai.structured(SYSTEM, content, GEN_SCHEMA, effort="high")

    by_name = {r.name.lower(): r for r in rooms}
    book_index = {(p.description.lower(), p.unit): p for p in book}
    sections = []
    for s in data["sections"]:
        items = []
        for it in s["items"]:
            unit = it["unit"].upper()
            match = book_index.get((it["price_book_match"].lower(), unit)) if it["price_book_match"] else None
            if match:
                price, source = match.median_price, "history"
            else:
                price, source = it["suggested_unit_price"], "ai"
            items.append(LineItem(
                category=it["category"], selector=it["selector"], description=it["description"],
                quantity=it["quantity"], unit=unit, unit_price=price, note=it["note"], price_source=source,
            ))
        sections.append(Section(name=s["name"], room=by_name.get(s["name"].lower()), option=s["option"],
                                items=items))

    est = Estimate(
        title=data["title"], loss_type=data["loss_type"], summary=data["summary"], sections=sections,
        customer=customer, address=address, claim_number=claim_number,
        overhead_pct=overhead_pct, profit_pct=profit_pct, tax_pct=tax_pct,
    )
    questions = list(data["questions"])
    if customer_scope:
        from .customer import write_customer_scope
        try:
            write_customer_scope(est, library.style_examples())
        except ai.AIError as e:
            fill_missing_trades(est)
            questions.append(f"Customer scope wasn't written ({e}); bullets fall back to line-item wording.")
    return est, questions
