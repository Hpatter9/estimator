"""Import Xactimate rate-sheet PDFs (a "PRICELIST_..." estimate exported from Xactimate) into the skill.

    py -m estimator import-pricelist PRICELIST_DENVER_FINAL_DRAFT_CON.pdf --components PRICELIST_DENVER_COMPONENTS_CON.pdf

Writes skill/forefront-estimate/references/xactimate_prices.csv (every line item on the list at this month's price
list, with REMOVE and REPLACE split) and component_costs.csv (material / equipment / labor components). Each file
holds one set of rows per price list (CODE8X_OCT26 for Denver, COBO8X_OCT26 for Boulder, ...); importing a list
replaces only that list's rows, so import each market you price in. R&R items
also produce their install-only ("Snaplock Laminate ...") and remove-only ("Remove Snaplock Laminate ...") rows,
priced from the REPLACE and REMOVE columns, the way Xactimate prices them.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

NUM = r"([\d,]+\.\d\d)"
ITEM = re.compile(rf"^\s*([\d,]+)\.\s+(.*?)\s+(?:1\.00\s+)?([A-Z]{{2,3}})\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}\s*$")
COMP = re.compile(r"^\s*(\S+)\s+(.*?)\s+([\d.]+)\s+([A-Z]{1,3})\s+@\s+([\d,]+\.\d+)\s+([\d,]+\.\d\d)\*?\s*$")
SKIP = re.compile(r"^\s*(DESCRIPTION|Totals:|CONTINUED|PRICELIST_|\d+\s*$|.*Page:\s*\d+)")
PRICE_LIST = re.compile(r"Price List:\s*(\S+)")


def _f(x: str) -> float:
    return float(x.replace(",", ""))


def pdf_text(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text(layout=True) or "") for p in pdf.pages)


def _letterhead_lines(lines: list[str]) -> set[str]:
    """Lines repeated at the top of most pages (the company letterhead) - skipped."""
    from collections import Counter
    c = Counter(ln.strip() for ln in lines if ln.strip())
    pages = sum(1 for ln in lines if "Page:" in ln)
    if pages < 3:
        return set()
    return {t for t, n in c.items() if n >= pages * 0.8 and not ITEM.match(t)}


def parse_items(text: str) -> list[dict]:
    lines = text.split("\n")
    head = _letterhead_lines(lines)
    rows, cat, last, started = [], "", None, False
    for ln in lines:
        m = ITEM.match(ln)
        if m:
            started = True
            n, desc, unit, rem, rep, _tax, _tot = m.groups()
            last = {"no": int(n.replace(",", "")), "category": cat or "Appliances", "description": desc.strip(),
                    "unit": unit, "remove": _f(rem), "replace": _f(rep)}
            rows.append(last)
            continue
        s = ln.strip()
        if not started or not s or s in head or SKIP.match(ln):
            if s.startswith("Totals:"):
                last = None
            continue
        indent = len(ln) - len(ln.lstrip())
        if last is not None and indent <= 8 and not re.search(r"\d\.\d\d\s*$", ln):
            last["description"] = f"{last['description']} {s}"
        elif indent > 20:
            cat, last = s, None
    for r in rows:
        r["description"] = re.sub(r"\s+", " ", r["description"])
    return rows


def parse_components(text: str) -> list[dict]:
    lines = text.split("\n")
    head = _letterhead_lines(lines)
    rows, last, section = [], None, ""
    for ln in lines:
        m = COMP.match(ln)
        if m:
            code, desc, _q, unit, up, _tot = m.groups()
            last = {"code": code, "description": desc.strip(), "unit": unit, "unit_price": _f(up), "section": section}
            rows.append(last)
            continue
        s = ln.strip()
        if not s or s in head or SKIP.match(ln) or s.startswith("Code "):
            continue
        if "COMPONENTS" in s and len(s.split()) <= 5:
            section = re.sub(r"\s+", " ", s.title()).replace("Continued - ", "")
            last = None
            continue
        if last is not None and (len(ln) - len(ln.lstrip())) > 12 and "@" not in ln:
            last["description"] = f"{last['description']} {s}"
    return rows


def price_rows(items: list[dict], price_list: str) -> list[dict]:
    """One row per description/unit, plus install-only and remove-only rows split out of R&R items."""
    out: dict[tuple[str, str], dict] = {}

    def add(desc, unit, remove, replace, cat, how):
        key = (desc.lower(), unit)
        if key in out and out[key]["source"] == "list":
            return
        out[key] = {"description": desc, "unit": unit, "price": round(remove + replace, 2), "remove": remove,
                    "replace": replace, "category": cat, "price_list": price_list, "source": how}

    for r in items:
        add(r["description"], r["unit"], r["remove"], r["replace"], r["category"], "list")
    for r in items:
        if r["description"].startswith("R&R "):
            base = r["description"][4:]
            if r["replace"] > 0:
                add(base, r["unit"], 0.0, r["replace"], r["category"], "replace column of R&R")
            if r["remove"] > 0:
                add(f"Remove {base}", r["unit"], r["remove"], 0.0, r["category"], "remove column of R&R")
    return sorted(out.values(), key=lambda r: (r["category"], r["description"]))


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def merge_csv(rows: list[dict], path: Path, price_list: str) -> None:
    """Replace this price list's rows in the file and keep the other markets' lists (Denver, Boulder, ...)."""
    old = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            old = [r for r in csv.DictReader(fh) if r.get("price_list") and r["price_list"] != price_list]
    write_csv(old + rows, path)


def import_pricelist(items_pdf: Path, components_pdf: Path | None, out_dir: Path) -> dict:
    text = pdf_text(items_pdf)
    m = PRICE_LIST.search(text)
    price_list = m.group(1) if m else items_pdf.stem
    items = parse_items(text)
    rows = price_rows(items, price_list)
    merge_csv(rows, out_dir / "xactimate_prices.csv", price_list)
    info = {"price_list": price_list, "list_items": len(items), "rows": len(rows)}
    if components_pdf:
        comps = [{**c, "price_list": price_list} for c in parse_components(pdf_text(components_pdf))]
        merge_csv(comps, out_dir / "component_costs.csv", price_list)
        info["components"] = len(comps)
    return info
