"""Build the shareable Claude skill (skill/forefront-estimate) from this program.

    py -m estimator build-skill            # -> dist/forefront-estimate.skill (upload it to Claude)

What it does:
  1. Regenerates the skill's reader scripts from estimator/ingest (so reader fixes reach the skill).
  2. Writes your price book (every line item you've used, the prices you charged - no customer
     names or addresses), your most-used items, and your typical markup from the local library.
  3. Zips skill/forefront-estimate into dist/forefront-estimate.skill.
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "forefront-estimate"
PKG = Path(__file__).resolve().parent

MODEL_SHIM = '''
# ---- minimal stand-ins for the estimator package's data models (keeps this script standalone) ----
@dataclass
class Room:
    name: str
    height_ft: float | None = None
    floor_sf: float | None = None
    ceiling_sf: float | None = None
    wall_sf: float | None = None
    perimeter_lf: float | None = None


@dataclass
class LineItem:
    description: str
    quantity: float = 0.0
    unit: str = "EA"
    unit_price: float = 0.0
    tax: float = 0.0
    note: str = ""
    group: str = ""
    price_source: str = ""


@dataclass
class Section:
    name: str
    room: Room | None = None
    items: list = field(default_factory=list)


@dataclass
class Estimate:
    title: str = ""
    customer: str = ""
    address: str = ""
    claim_number: str = ""
    loss_type: str = ""
    price_list: str = ""
    summary: str = ""
    source_file: str = ""
    overhead_pct: float = 10.0
    profit_pct: float = 10.0
    sections: list = field(default_factory=list)
'''

XACT_HEADER = '''#!/usr/bin/env python3
"""Read an Xactimate estimate PDF into line items - no AI. (Generated from estimator/ingest/xactimate_pdf.py;
edit that file and run `py -m estimator build-skill`, not this one.)

    python read_xactimate.py estimate.pdf                 # summary + room checks
    python read_xactimate.py estimate.pdf --json est.json # write sections/items for render.py

Every room's items are checked against the printed "Totals:" line; the summary says whether they match.
"""
'''

XACT_MAIN = '''

def to_json(result: "ParseResult") -> dict:
    est = result.estimate
    return {
        "estimate_number": est.title, "customer": est.customer, "address": est.address,
        "claim_number": est.claim_number, "loss_type": est.loss_type, "price_list": est.price_list,
        "overhead_pct": est.overhead_pct, "profit_pct": est.profit_pct,
        "rooms": [vars(s.room) | {"name": s.name} for s in est.sections if s.room],
        "sections": [{"name": s.name, "option": "", "items": [
            {"description": i.description, "quantity": i.quantity, "unit": i.unit, "unit_price": i.unit_price,
             "tax": i.tax, "note": i.note, "group": i.group, "trade": "", "price_source": "xactimate"}
            for i in s.items]} for s in est.sections],
        "check": result.report(), "printed_total": result.printed_total,
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys
    p = argparse.ArgumentParser()
    p.add_argument("pdf", type=Path)
    p.add_argument("--json", type=Path)
    a = p.parse_args()
    r = parse_xactimate(a.pdf)
    data = to_json(r)
    n = sum(len(s["items"]) for s in data["sections"])
    print(f"{data['estimate_number']}: {n} line items in {len(data['sections'])} sections - {data['check']}")
    print(f"Printed total (incl. O&P): {data['printed_total']}")
    for s in data["sections"]:
        print(f"  {s['name']}: {len(s['items'])} items")
    if a.json:
        a.json.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Saved to {a.json}")
    sys.exit(0)
'''


def generated_read_xactimate() -> str:
    src = (PKG / "ingest" / "xactimate_pdf.py").read_text(encoding="utf-8")
    src = src.split('"""', 2)[2]  # drop the package docstring
    src = src.replace("from ..models import Estimate, LineItem, Room, Section\n", MODEL_SHIM)
    return XACT_HEADER + src.lstrip("\n").rstrip() + "\n" + XACT_MAIN


def generated_read_esx() -> str:
    """read_esx.py = the package's geometry code + a small command line."""
    src = (PKG / "ingest" / "esx.py").read_text(encoding="utf-8")
    geo = src[src.index("UNITS_PER_FT = 1524.0"):src.index("def read_esx")]
    start, end = geo.index("    def to_room(self)"), geo.index("def _sketch_xml")
    geo = geo[:start].rstrip() + "\n\n\n" + geo[end:]
    body = src[src.index("def read_esx"):src.index("def load_esx_rooms")]
    template = (SKILL / "scripts" / "_read_esx_cli.py.txt").read_text(encoding="utf-8")
    head, tail = template.split("# @@GEOMETRY@@\n")
    return head + geo + body.rstrip() + "\n" + tail


# ---------------- price book from the local library ----------------

def price_book_rows(library) -> list[dict]:
    """Every distinct line item with the prices you've charged. No customer data."""
    groups: dict[tuple[str, str], list] = defaultdict(list)
    trade_votes: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in library.list():
        est = library.get(r["id"])
        for _, item in est.all_items():
            if item.unit_price <= 0:
                continue
            key = (_norm(item.description), item.unit.upper())
            groups[key].append((item.description, item.unit_price, item.quantity, est.estimate_date))
            if item.group:
                trade_votes[key][item.group] += 1
    rows = []
    for key, uses in groups.items():
        prices = [u[1] for u in uses]
        latest = max(uses, key=lambda u: str(u[3]))
        rows.append({
            "description": latest[0], "unit": key[1],
            "median_price": round(statistics.median(prices), 2), "latest_price": round(latest[1], 2),
            "min_price": round(min(prices), 2), "max_price": round(max(prices), 2),
            "times_used": len(uses), "typical_qty": round(statistics.median(u[2] for u in uses), 2),
            "xactimate_group": trade_votes[key].most_common(1)[0][0] if trade_votes[key] else "",
        })
    rows.sort(key=lambda r: (-r["times_used"], r["description"]))
    return rows


def _norm(d: str) -> str:
    d = re.sub(r"^\s*[\d,]+\.\s*", "", d.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/\"' ]+", " ", d)).strip()


def write_price_book(rows: list[dict], out_dir: Path, markup: float | None, n_estimates: int) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["description"])
    w.writeheader()
    w.writerows(rows)
    (out_dir / "price_book.csv").write_text(buf.getvalue(), encoding="utf-8")

    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in rows[:400]:
        by_group[r["xactimate_group"] or "Other"].append(r)
    lines = ["# Most-used line items", "",
             f"From {n_estimates} past Xactimate estimates. The full list is price_book.csv; search it with "
             "`python scripts/price_lookup.py <words>`. Prices are per unit, before O&P.", ""]
    if markup is not None:
        lines += [f"Typical markup of customer documents over the Xactimate: **{markup:.1f}%**.", ""]
    for group in sorted(by_group, key=lambda g: -sum(r["times_used"] for r in by_group[g])):
        lines += [f"## {group}", "", "| Item | Unit | Typical price | Used |", "|---|---|---|---|"]
        lines += [f"| {r['description']} | {r['unit']} | ${r['median_price']:,.2f} | {r['times_used']}x |"
                  for r in by_group[group]]
        lines.append("")
    (out_dir / "common_items.md").write_text("\n".join(lines), encoding="utf-8")
    meta = {"estimates": n_estimates, "line_items": len(rows), "markup_pct": markup}
    (out_dir / "price_book_info.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def regenerate_scripts() -> None:
    (SKILL / "scripts" / "read_xactimate.py").write_text(generated_read_xactimate(), encoding="utf-8")
    (SKILL / "scripts" / "read_esx.py").write_text(generated_read_esx(), encoding="utf-8")


def package(out: Path, src: Path = SKILL) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith("_"):
                z.write(f, Path(SKILL.name) / f.relative_to(src))
    return out


def build(library, company, out: Path) -> dict:
    """Builds in a copy (dist/forefront-estimate/) so the files tracked in git never change here."""
    import shutil
    from .markup import default_markup, suggested
    stage = out.parent / SKILL.name
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(SKILL, stage, ignore=shutil.ignore_patterns("__pycache__", "_*"))
    (stage / "scripts" / "read_xactimate.py").write_text(generated_read_xactimate(), encoding="utf-8")
    (stage / "scripts" / "read_esx.py").write_text(generated_read_esx(), encoding="utf-8")
    rows = price_book_rows(library)
    markup = company.markup_pct if company.markup_pct is not None else suggested(library)
    if rows:
        write_price_book(rows, stage / "references", markup, library.count())
    company_data = json.loads(company.model_dump_json())
    company_data["markup_pct"] = default_markup(library, company)
    (stage / "assets" / "company.json").write_text(json.dumps(company_data, indent=2, ensure_ascii=False),
                                                   encoding="utf-8")
    package(out, stage)
    return {"line_items": len(rows), "estimates": library.count(), "markup": company_data["markup_pct"], "file": out}
