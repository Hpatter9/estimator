"""Command line:

  python -m estimator import  past_estimates/*.pdf          # teach it your past jobs
  python -m estimator list                                  # what's in the library
  python -m estimator prices                                # your price book
  python -m estimator new --notes notes.txt --sketch docusketch.pdf --photos pics/*.jpg \
                          --customer "Jane Doe" --format xactimate --format company
  python -m estimator export output/job.json --format excel # re-export an edited estimate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_company
from .export import FORMATS, export
from .library import DEFAULT_DB, Library

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="estimator", description="Build new estimates from your past ones.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="library database (default data/library.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="add past estimates (PDF, CSV, XLSX, JSON) to the library")
    imp.add_argument("files", nargs="+", type=Path)
    imp.add_argument("--no-ai", action="store_true", help="parse PDFs with the offline Xactimate parser instead of Claude")

    sub.add_parser("list", help="list estimates in the library")
    pr = sub.add_parser("prices", help="show your price book")
    pr.add_argument("--search", default="")

    new = sub.add_parser("new", help="draft a new estimate")
    new.add_argument("--notes", type=Path, required=True, help="text file with your job notes")
    new.add_argument("--sketch", type=Path, action="append", default=[],
                     help="DocuSketch export (PDF, CSV, XLSX, ESX/ZIP, JSON); repeatable")
    new.add_argument("--photos", type=Path, nargs="*", default=[])
    new.add_argument("--attach", type=Path, nargs="*", default=[], help="other PDFs to read (scope sheets, adjuster notes)")
    new.add_argument("--customer", default="")
    new.add_argument("--address", default="")
    new.add_argument("--claim", default="")
    new.add_argument("--overhead", type=float, default=10.0)
    new.add_argument("--profit", type=float, default=10.0)
    new.add_argument("--tax", type=float, default=0.0)
    new.add_argument("--format", action="append", choices=list(FORMATS), help="output format(s); repeatable")
    new.add_argument("--out", type=Path, default=Path("output"))
    new.add_argument("--save", action="store_true", help="also add the new estimate to the library")

    ex = sub.add_parser("export", help="export a saved estimate JSON to other formats")
    ex.add_argument("estimate", type=Path)
    ex.add_argument("--format", action="append", choices=list(FORMATS), required=True)
    ex.add_argument("--out", type=Path, default=Path("output"))

    args = p.parse_args(argv)
    lib = Library(args.db)

    if args.cmd == "import":
        from .ingest import load_past_estimate
        for f in args.files:
            try:
                est = load_past_estimate(f, use_ai=not args.no_ai)
            except Exception as e:  # keep going through a batch
                print(f"  ! {f.name}: {e}", file=sys.stderr)
                continue
            eid = lib.add(est)
            n = sum(len(s.items) for s in est.sections)
            print(f"  + #{eid} {f.name}: {n} line items, total ${est.grand_total:,.2f}")
        return 0

    if args.cmd == "list":
        for r in lib.list():
            print(f"#{r['id']:<4} {r['title'] or r['source_file']:<45} {r['loss_type'] or '':<12} ${r['grand_total']:>12,.2f}")
        return 0

    if args.cmd == "prices":
        for e in lib.price_book():
            if args.search.lower() in e.description.lower():
                print(f"{e.category:<5} {e.description[:60]:<60} {e.unit:<3} ${e.median_price:>9,.2f}  x{e.times_used}")
        return 0

    if args.cmd == "new":
        from .generate import generate_estimate
        from .ingest.docusketch import load_rooms
        rooms = [r for s in args.sketch for r in load_rooms(s)]
        print(f"Read {len(rooms)} rooms from DocuSketch; library has {lib.count()} past estimates.")
        est, questions = generate_estimate(
            lib, args.notes.read_text(), rooms, photos=args.photos, extra_files=args.attach,
            customer=args.customer, address=args.address, claim_number=args.claim,
            overhead_pct=args.overhead, profit_pct=args.profit, tax_pct=args.tax,
        )
        _report(est, questions)
        paths = export(est, "json", args.out, load_company())
        for fmt in args.format or ["xactimate"]:
            paths += export(est, fmt, args.out, load_company())
        for pth in paths:
            print(f"  -> {pth}")
        if args.save:
            lib.add(est)
        return 0

    if args.cmd == "export":
        from .models import Estimate
        est = Estimate.model_validate_json(args.estimate.read_text())
        for fmt in args.format:
            for pth in export(est, fmt, args.out, load_company()):
                print(f"  -> {pth}")
        return 0
    return 1


def _report(est, questions):
    ai_priced = [i for _, i in est.all_items() if i.price_source == "ai"]
    n = sum(len(s.items) for s in est.sections)
    print(f"\n{est.title}: {n} line items in {len(est.sections)} areas, total ${est.grand_total:,.2f}")
    if ai_priced:
        print(f"  {len(ai_priced)} items had no match in your price history - check their prices:")
        for i in ai_priced:
            print(f"    - {i.description} ({i.unit}) @ ${i.unit_price:,.2f}")
    if questions:
        print("  Questions to confirm:")
        for q in questions:
            print(f"    ? {q}")


if __name__ == "__main__":
    raise SystemExit(main())
