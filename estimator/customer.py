"""Turn Xactimate-style line items into your customer-facing scope: which trade each item belongs
to, the plain-English bullets under each trade, the note under each trade, and the intro box.

This is the step you do by hand today when you turn an Xactimate estimate into a Reconstruction
Estimate / Agreement. It learns your wording from the customer documents in your library
(any Reconstruction Estimate / Agreement PDFs you import).
"""
from __future__ import annotations

from . import ai
from .models import Estimate, ScopeText, TradeText
from .trades import DEFAULT_NOTES, TRADE_ORDER, guess_trade

SCHEMA = ai.obj({
    "intro": ai.STR,
    "scopes": {"type": "array", "items": ai.obj({"option": ai.STR, "areas": ai.STR})},
    "trades": {"type": "array", "items": ai.obj({
        "option": ai.STR,
        "trade": ai.STR,
        "items": {"type": "array", "items": {"type": "integer"}},
        "bullets": {"type": "array", "items": ai.STR},
        "note": ai.STR,
    })},
})

STYLE_GUIDE = f"""House style for the customer scope (follow it closely):
- Trades, in this order when present: {", ".join(TRADE_ORDER)}.
  Name flooring by material when it is one material, e.g. "Flooring — Luxury Vinyl Plank", "Flooring — Carpet".
  Use "Plumbing / Shower" when there is shower/tub work, otherwise "Plumbing".
- Every line item goes into exactly one trade. Put an item where a homeowner would expect it, not where
  Xactimate grouped it: sinks, faucets, angle stops, supply lines, P-traps, disposers, toilets and tubs are
  Plumbing; a range hood is Appliances; casing, doors, baseboard and shelving are Finish Carpentry / Trim;
  haul debris, cleaning, supervision, dust containment, contents and labor minimums are Demolition & General
  Conditions unless a minimum clearly belongs to one trade.
- Bullets: short, plain English, start with a verb, no Xactimate codes, quantities or units. Combine the same
  work across rooms into one bullet. Add " — Room" (em dash) only when the work is limited to specific areas
  and that matters to the customer. Mention material and size when it matters (e.g. "Install new baseboard —
  3 1/4\\" MDF, flat profile"). Masking/protection items become one bullet such as "Mask walls and protect
  floors and surrounding finishes during drywall work".
- Note: one or two sentences that set expectations, using the standard note when it applies and adding a
  job-specific sentence when the estimator's line-item notes give one (e.g. popcorn texture blended rather
  than scraped). Leave the note empty when nothing applies. Standard notes:
{chr(10).join(f"    {k}: {v}" for k, v in DEFAULT_NOTES.items())}
- scopes: for the base scope (option "") and each optional add-on, list the areas covered in one short phrase,
  e.g. "Kitchen, Living Room, Hallway and closets, and Bedroom 1 and closet". Capitalize room names.
- intro: only when there are optional add-ons - one or two sentences starting "How this estimate is
  organized." explaining what the base scope covers and that the add-ons are priced separately and not
  part of the Total Job Price unless accepted. Otherwise "".
"""


def _items_table(est: Estimate) -> tuple[str, list]:
    rows, refs = [], []
    for section, item in est.all_items():
        refs.append((section, item))
        note = f" | note: {item.note}" if item.note else ""
        rows.append(f"{len(refs)}. [{section.option or 'base'}] [{section.name}] [{item.group}] "
                    f"{item.description} | {item.quantity:g} {item.unit}{note}")
    return "\n".join(rows), refs


def write_customer_scope(est: Estimate, style_examples: list[str] = ()) -> Estimate:
    """Fills item.trade, est.trade_text, est.scope_text and est.intro (in place) and returns est."""
    table, refs = _items_table(est)
    content = []
    if style_examples:
        content.append({"type": "text", "text": "Examples of the company's finished customer estimates (match this "
                        "wording and level of detail):\n\n" + "\n\n---\n\n".join(style_examples[:3]),
                        "cache_control": {"type": "ephemeral"}})
    content.append({"type": "text", "text": f"Job: {est.title} at {est.address}\n\nLine items "
                    "(number. [base or optional add-on name] [room] [Xactimate group] description | qty | note):\n"
                    + table + "\n\nWrite the customer scope."})
    system = ("You write the customer-facing scope of work for a restoration/reconstruction contractor, turning "
              "their Xactimate line items into clear trade sections a homeowner can read.\n\n" + STYLE_GUIDE)
    data = ai.structured(system, content, SCHEMA, effort="medium")

    assigned = set()
    for t in data["trades"]:
        for n in t["items"]:
            if 1 <= n <= len(refs) and n not in assigned:
                refs[n - 1][1].trade = t["trade"]
                assigned.add(n)
    for n, (_, item) in enumerate(refs, 1):
        if n not in assigned:
            item.trade = guess_trade(item)
    opt = lambda o: o if o in est.options else ""  # "base" / unknown -> base scope
    est.trade_text = [TradeText(trade=t["trade"], option=opt(t["option"]), bullets=t["bullets"], note=t["note"])
                      for t in data["trades"]]
    est.scope_text = [ScopeText(option=opt(s["option"]), areas=s["areas"]) for s in data["scopes"]]
    if est.options:
        est.intro = data["intro"]
    return est
