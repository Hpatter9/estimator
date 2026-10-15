#!/usr/bin/env python3
"""Search Forefront's prices: the current Xactimate price list plus every line item Forefront has used.

    python price_lookup.py drywall 1/2              # items matching all the words
    python price_lookup.py "baseboard" --unit LF
    python price_lookup.py vanity --limit 40
    python price_lookup.py snaplock --list COBO8X_OCT26   # only the Boulder list
    python price_lookup.py --components laminate     # material / equipment / labor component costs

One price column per Xactimate price list in references/xactimate_prices.csv (CODE8X_OCT26 = Denver,
COBO8X_OCT26 = Boulder, ...); `median` / `latest` / `used` come from Forefront's past estimates
(references/price_book.csv). Prices are per unit, before O&P. Copy the description and unit exactly into
estimate.json and price it from the job's market list when the item is on it (price_source "price_list");
otherwise use `median` (price_source "price_book").
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "references"
BOOK = REF / "price_book.csv"
LIST = REF / "xactimate_prices.csv"
COMPONENTS = REF / "component_costs.csv"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _match(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def components(words: list[str], unit: str | None, limit: int, plist: str | None) -> int:
    rows = [r for r in _read(COMPONENTS) if not plist or r.get("price_list", "") == plist]
    hits = [r for r in rows if _match((r["code"] + " " + r["description"]).lower(), words) == len(words)
            and (not unit or r["unit"].upper() == unit.upper())]
    if not hits:
        print(f"No component costs match {' '.join(words)!r}.")
        return 1
    print(f"{'code':<14} {'description':<56} {'unit':<4} {'price':>10}  list")
    for r in hits[:limit]:
        print(f"{r['code']:<14} {r['description'][:56]:<56} {r['unit']:<4} {float(r['unit_price']):>10,.2f}  "
              f"{r.get('price_list', '')}")
    if len(hits) > limit:
        print(f"... {len(hits) - limit} more; add words or --limit")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("words", nargs="+")
    p.add_argument("--unit")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--components", action="store_true", help="search material/equipment/labor component costs")
    p.add_argument("--list", dest="plist", help="only this price list, e.g. COBO8X_OCT26 (Boulder)")
    a = p.parse_args(argv)
    words = [w.lower() for w in a.words]
    if a.components:
        return components(words, a.unit, a.limit, a.plist)

    book = {(r["description"].lower(), r["unit"].upper()): r for r in _read(BOOK)}
    lists: dict[str, dict] = {}
    for r in _read(LIST):
        if not a.plist or r["price_list"] == a.plist:
            lists.setdefault(r["price_list"], {})[(r["description"].lower(), r["unit"].upper())] = r
    names = sorted(lists)
    plist = {k: v for name in names for k, v in lists[name].items()}
    hits = []
    for key in set(book) | set(plist):
        desc, unit = key
        if a.unit and unit != a.unit.upper():
            continue
        score = _match(desc, words)
        if not score or (score < len(words) and len(words) == 1):
            continue
        used = int(book[key]["times_used"]) if key in book else 0
        rank = (0 if score == len(words) else 1, -score, -used, 0 if key in plist else 1, len(desc))
        hits.append((rank, key))
    hits.sort()
    if not hits:
        print(f"No items match {' '.join(a.words)!r}. Try fewer or different words "
              "(Xactimate wording, e.g. 'R&R', 'Detach & reset', 'drywall - hung').")
        return 1
    head = "".join(f" {n[:12]:>12}" for n in names)
    print(f"{'description':<62} {'unit':<4}{head} {'median':>9} {'latest':>9} {'used':>5}")
    for _, key in hits[:a.limit]:
        b = book.get(key)
        name = (b or plist[key])["description"]
        fmt = lambda r, k, w=9: f"{float(r[k]):>{w},.2f}" if r else f"{'-':>{w}}"
        cols = "".join(" " + fmt(lists[n].get(key), "price", 12) for n in names)
        print(f"{name[:62]:<62} {key[1]:<4}{cols} {fmt(b, 'median_price')} {fmt(b, 'latest_price')} "
              f"{(b['times_used'] if b else '0'):>5}")
    if len(hits) > a.limit:
        print(f"... {len(hits) - a.limit} more; add words or --limit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
