"""How much you marked up customer documents over the Xactimate, job by job.

Pairs each imported customer Estimate / Agreement with the Xactimate estimate it names
("Estimate: SMITH_123_REC") and compares the base totals.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .library import Library

TOTAL_RE = re.compile(r"(?:Total Job Price(?: \(Base Scope\))?|Total Agreement Amount|Total Contract Amount:)\s*\$\s*([\d,]+\.\d{2})")


@dataclass
class MarkupRow:
    estimate: str
    xactimate_total: float
    customer_total: float

    @property
    def pct(self) -> float:
        return round((self.customer_total / self.xactimate_total - 1) * 100, 1)


def history(library: Library) -> list[MarkupRow]:
    by_title = {r["title"].upper(): r for r in library.list() if r["title"]}
    rows = []
    for text in library.style_examples(limit=100000):
        m = TOTAL_RE.search(text)
        if not m:
            continue
        customer_total = float(m[1].replace(",", ""))
        for name in re.findall(r"\b[A-Z][A-Z0-9]*_\d+_[A-Z0-9]+\b", text):
            est = by_title.get(name)
            if est and est["grand_total"]:
                rows.append(MarkupRow(name, est["grand_total"], customer_total))
                break
    return rows


def suggested(library: Library) -> float | None:
    rows = history(library)
    return statistics.median(r.pct for r in rows) if rows else None


def default_markup(library: Library, company) -> float:
    """Company setting if set, else the median of past jobs, else 0."""
    if company.markup_pct is not None:
        return company.markup_pct
    return suggested(library) or 0.0
