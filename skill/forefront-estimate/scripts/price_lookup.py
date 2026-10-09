#!/usr/bin/env python3
"""Search the price book (references/price_book.csv) - every line item Forefront has used, with prices.

    python price_lookup.py drywall 1/2              # items matching all the words
    python price_lookup.py "baseboard" --unit LF
    python price_lookup.py vanity --limit 40

Prices are per unit, before O&P. Copy the description and unit exactly into estimate.json and use
median_price (or latest_price when the job is recent and the two differ a lot).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parent.parent / "references" / "price_book.csv"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("words", nargs="+")
    p.add_argument("--unit")
    p.add_argument("--limit", type=int, default=25)
    a = p.parse_args(argv)
    words = [w.lower() for w in a.words]
    with open(BOOK, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    hits = []
    for r in rows:
        text = r["description"].lower()
        if a.unit and r["unit"].upper() != a.unit.upper():
            continue
        score = sum(1 for w in words if w in text)
        if score == len(words):
            hits.append((-int(r["times_used"]), r))
        elif score and len(words) > 1:
            hits.append((1000 - score * 100 - int(r["times_used"]), r))
    hits.sort(key=lambda h: h[0])
    if not hits:
        print(f"No price-book items match {' '.join(a.words)!r}. Try fewer or different words "
              "(Xactimate wording, e.g. 'R&R', 'Detach & reset', 'drywall - hung').")
        return 1
    print(f"{'description':<70} {'unit':<4} {'median':>9} {'latest':>9} {'range':>19} {'used':>5}")
    for _, r in hits[:a.limit]:
        rng = f"{float(r['min_price']):,.2f}-{float(r['max_price']):,.2f}"
        print(f"{r['description'][:70]:<70} {r['unit']:<4} {float(r['median_price']):>9,.2f} "
              f"{float(r['latest_price']):>9,.2f} {rng:>19} {r['times_used']:>5}")
    if len(hits) > a.limit:
        print(f"... {len(hits) - a.limit} more; add words or --limit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
