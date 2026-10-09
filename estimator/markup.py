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
    by_title: dict[str, list] = {}
    for r in library.list():
        if r["title"]:
            by_title.setdefault(r["title"].upper(), []).append(r)
    rows = []
    for text in library.style_examples(limit=100000):
        m = TOTAL_RE.search(text)
        if not m:
            continue
        customer_total = float(m[1].replace(",", ""))
        names = list(dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9]*_\d+_[A-Z0-9]+\b", text)))
        # Only pair when the document names exactly one Xactimate and exactly that one was imported.
        # A document naming several (e.g. an HOA portion plus the full job) covers more than any one of
        # them; and two imported revisions under the same name can't be told apart.
        if len(names) != 1 or len(by_title.get(names[0], [])) != 1:
            continue
        est = by_title[names[0]][0]
        if est["grand_total"]:
            rows.append(MarkupRow(names[0], est["grand_total"], customer_total))
    return rows


def suggested(library: Library) -> float | None:
    """Median markup, counting each job once (revisions of one customer document are averaged)."""
    per_job: dict[str, list[float]] = {}
    for r in history(library):
        per_job.setdefault(r.estimate, []).append(r.pct)
    return statistics.median(statistics.mean(v) for v in per_job.values()) if per_job else None


def jobs(library: Library) -> int:
    return len({r.estimate for r in history(library)})


def default_markup(library: Library, company) -> float:
    """Company setting if set, else the median of past jobs, else 0."""
    if company.markup_pct is not None:
        return company.markup_pct
    return suggested(library) or 0.0
