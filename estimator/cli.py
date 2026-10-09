"""Command line:

  python -m estimator import "C:/Estimates"                 # whole folder (subfolders too); safe to re-run
  python -m estimator list                                   # what's in the library
  python -m estimator prices --search drywall                # your price book
  python -m estimator new --notes notes.txt --sketch job.ESX --height "Kitchen=10" --photos pics/*.jpg \\
                          --customer "Jane Doe" --address "123 Main St, Denver, CO 80211"
  python -m estimator convert xactimate.pdf --optional "Pantry=Pantry Repairs"
                                                             # Xactimate PDF -> your Estimate + Agreement
  python -m estimator export output/job.json --format agreement   # re-export an edited estimate
  python -m estimator markup                                 # your markup on past jobs
  python -m estimator build-skill                            # -> dist/forefront-estimate.skill for Claude
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_company
from .export import FORMATS, export
from .library import DEFAULT_DB, Library

DEFAULT_FORMATS = ["xactimate", "estimate", "agreement"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="estimator", description="Build new estimates from your past ones.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="library database (default data/library.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="add past estimates and customer documents (files or folders)")
    imp.add_argument("paths", nargs="+", type=Path)
    imp.add_argument("--no-ai", action="store_true",
                     help="never call Claude: Xactimate PDFs only (free); other PDFs are skipped")

    sub.add_parser("list", help="list what's in the library")
    bs = sub.add_parser("build-skill", help="build the Claude skill file from your library (price book, markup)")
    bs.add_argument("--out", type=Path, default=Path("dist/forefront-estimate.skill"))
    bs.add_argument("--markup", type=float, help="markup %% for customer documents (saved as your company setting)")
    sub.add_parser("markup", help="show how much you marked up past customer documents over the Xactimate")
    pr = sub.add_parser("prices", help="show your price book")
    pr.add_argument("--search", default="")

    new = sub.add_parser("new", help="draft a new estimate from notes + DocuSketch")
    new.add_argument("--notes", type=Path, required=True, help="text file with your job notes")
    new.add_argument("--sketch", type=Path, action="append", default=[],
                     help="DocuSketch file: .ESX (best), PDF, CSV/XLSX; repeatable")
    new.add_argument("--photos", type=Path, nargs="*", default=[])
    new.add_argument("--attach", type=Path, nargs="*", default=[], help="other PDFs to read (scope sheets, adjuster notes)")
    new.add_argument("--customer", default="")
    new.add_argument("--address", default="")
    new.add_argument("--claim", default="")
    new.add_argument("--tax", type=float, default=0.0)
    new.add_argument("--height", action="append", default=[], metavar="ROOM=FEET",
                     help='ceiling height for a room, e.g. "Kitchen=10" or "Kitchen=8.75"; repeatable '
                          "(DocuSketch exports every room at 8')")
    new.add_argument("--default-height", type=float, help="ceiling height for every room not given with --height")
    new.add_argument("--format", action="append", choices=list(FORMATS), help="output format(s); repeatable")
    new.add_argument("--out", type=Path, default=Path("output"))
    new.add_argument("--markup", type=float, help="markup %% on the customer Estimate / Agreement "
                        "(default: company setting, else the median of your past jobs)")
    new.add_argument("--save", action="store_true", help="also add the new estimate to the library")

    conv = sub.add_parser("convert", help="turn an Xactimate PDF into your customer Estimate / Agreement")
    conv.add_argument("pdf", type=Path)
    conv.add_argument("--optional", action="append", default=[], metavar="ROOM[=NAME]",
                      help='price a room as an optional add-on, e.g. "Pantry=Pantry Repairs"; repeatable')
    conv.add_argument("--no-ai", action="store_true", help="skip Claude; bullets use the Xactimate wording")
    conv.add_argument("--format", action="append", choices=list(FORMATS))
    conv.add_argument("--out", type=Path, default=Path("output"))
    conv.add_argument("--markup", type=float, help="markup %% on the customer Estimate / Agreement "
                        "(default: company setting, else the median of your past jobs)")

    ex = sub.add_parser("export", help="export a saved estimate JSON to other formats")
    ex.add_argument("estimate", type=Path)
    ex.add_argument("--format", action="append", choices=list(FORMATS), required=True)
    ex.add_argument("--out", type=Path, default=Path("output"))
    ex.add_argument("--markup", type=float, help="markup %% on the customer Estimate / Agreement "
                        "(default: company setting, else the median of your past jobs)")

    args = p.parse_args(argv)
    lib = Library(args.db)
    company = load_company()

    if args.cmd == "import":
        from .ingest import import_into_library
        counts = import_into_library(lib, args.paths, use_ai=not args.no_ai)
        print(f"\nDone: {counts['estimate']} estimates, {counts['style']} customer documents, "
              f"{counts['duplicate']} already imported, {counts['skipped']} skipped, {counts['error']} errors.")
        return 0 if counts["error"] == 0 else 1

    if args.cmd == "list":
        for r in lib.list():
            print(f"#{r['id']:<4} {r['title'] or r['source_file']:<45} {r['loss_type'] or '':<12} ${r['grand_total']:>12,.2f}")
        styles = lib.list_style_examples()
        print(f"\n{lib.count()} estimates, {len(styles)} customer documents (style examples).")
        return 0

    if args.cmd == "build-skill":
        from .skill_build import build
        if args.markup is not None:
            from .config import save_company
            company = company.model_copy(update={"markup_pct": args.markup})
            save_company(company)
        info = build(lib, company, args.out)
        print(f"Price book: {info['line_items']} line items from {info['estimates']} estimates; markup {info['markup']:g}%")
        print(f"Skill file: {info['file']}")
        print("Upload it in Claude: Settings > Capabilities > Skills > Upload skill.")
        return 0

    if args.cmd == "markup":
        from .markup import history, suggested
        rows = history(lib)
        for r in rows:
            print(f"{r.estimate:<30} Xactimate ${r.xactimate_total:>11,.2f}  customer ${r.customer_total:>11,.2f}  {r.pct:+.1f}%")
        from .markup import jobs
        n = jobs(lib)
        print(f"\nMedian markup: {suggested(lib):.1f}% from {n} job{'s' * (n != 1)}" if rows else
              "No pairs found. Import the Xactimate and the customer Estimate/Agreement for the same jobs.")
        if rows and n < 5:
            print("That's too few jobs to rely on. Customer documents are only paired when they name their "
                  "Xactimate (\"Estimate: SMITH_123_REC\"). Set markup_pct in data/company.json to fix the markup.")
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
        heights = {k.strip().lower(): float(v) for k, _, v in (h.partition("=") for h in args.height)}
        for room in rooms:
            h = heights.pop(room.name.lower(), args.default_height)
            if h:
                room.set_height(h)
        for name in heights:
            print(f"  ! --height: no room named {name!r}")
        print(f"Read {len(rooms)} rooms from DocuSketch; library has {lib.count()} past estimates.")
        est, questions = generate_estimate(
            lib, args.notes.read_text(encoding="utf-8-sig"), rooms, photos=args.photos, extra_files=args.attach,
            customer=args.customer, address=args.address, claim_number=args.claim,
            overhead_pct=company.overhead_pct, profit_pct=company.profit_pct, tax_pct=args.tax,
        )
        if rooms and not args.height and not args.default_height and all(r.height_ft == 8 for r in rooms):
            questions.append("Every room is at DocuSketch's default 8' ceiling. If any are taller, re-run with "
                             '--height "Room=10" so wall quantities are right.')
        est.markup_pct = _markup(args, lib, company)
        _report(est, questions)
        _write(est, args.format or DEFAULT_FORMATS, args.out, company)
        if args.save:
            lib.add(est)
        return 0

    if args.cmd == "convert":
        from .ingest.xactimate_pdf import parse_xactimate
        parsed = parse_xactimate(args.pdf)
        est = parsed.estimate
        print(f"Read {sum(len(s.items) for s in est.sections)} line items ({parsed.report()}).")
        for spec in args.optional:
            room, _, name = spec.partition("=")
            hits = [s for s in est.sections if s.name.lower() == room.strip().lower()]
            if not hits:
                print(f"  ! no room named {room!r}; rooms are: {', '.join(s.name for s in est.sections)}")
            for s in hits:
                s.option = name.strip() or f"{s.name} Repairs"
        if args.no_ai:
            from .trades import fill_missing_trades
            fill_missing_trades(est)
        else:
            from .customer import write_customer_scope
            write_customer_scope(est, lib.style_examples())
        est.estimate_numbers = est.estimate_numbers or [est.title]
        est.markup_pct = _markup(args, lib, company)
        print(f"Customer documents marked up {est.markup_pct:g}%.")
        _write(est, args.format or ["estimate", "agreement"], args.out, company)
        return 0

    if args.cmd == "export":
        from .models import Estimate
        est = Estimate.model_validate_json(args.estimate.read_text(encoding="utf-8"))
        if args.markup is not None:
            est.markup_pct = args.markup
        _write(est, args.format, args.out, company, save_json=False)
        return 0
    return 1


def _markup(args, lib, company) -> float:
    if args.markup is not None:
        return args.markup
    from .markup import default_markup
    return default_markup(lib, company)


def _write(est, formats, out, company, save_json=True):
    paths = export(est, "json", out, company) if save_json else []
    for fmt in formats:
        paths += export(est, fmt, out, company)
    for pth in paths:
        print(f"  -> {pth}")


def _report(est, questions):
    ai_priced = [i for _, i in est.all_items() if i.price_source == "ai"]
    n = sum(len(s.items) for s in est.sections)
    print(f"\n{est.title}: {n} line items in {len(est.sections)} areas, total ${est.grand_total:,.2f}"
          f" (customer documents +{est.markup_pct:g}% markup)")
    for o in est.options:
        print(f"  optional {o}: ${est.scope_total(o):,.2f}")
    if ai_priced:
        print(f"  {len(ai_priced)} items had no match in your price history - check their prices:")
        for i in ai_priced:
            print(f"    - {i.description} ({i.unit}) @ ${i.unit_price:,.2f}")
    if questions:
        print("  Questions to confirm:")
        for q in questions:
            print(f"    ? {q}")


if __name__ == "__main__":
    sys.exit(main())
