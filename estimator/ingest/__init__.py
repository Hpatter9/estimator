"""Importers: turn your files into Estimate / Room objects, and bulk-import whole folders.

What happens to each file:
  * Xactimate PDF            -> read offline (free); every room total is checked against the PDF.
                                If a check fails and AI is allowed, Claude re-reads the PDF instead.
  * Reconstruction Estimate / Agreement / Contract PDFs (your customer documents)
                             -> saved as style examples, so new customer scopes are written your way
  * Other PDFs               -> read by Claude (needs AI)
  * CSV / XLSX / JSON        -> read directly
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..models import Estimate

ESTIMATE_SUFFIXES = {".pdf", ".csv", ".xlsx", ".xlsm", ".json"}


@dataclass
class ImportResult:
    path: Path
    status: str  # "estimate", "style", "skipped", "duplicate", "error"
    message: str
    estimate: Estimate | None = None
    text: str = ""
    kind: str = ""
    file_hash: str = ""


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify_pdf(path: Path) -> str:
    """'xactimate', 'customer_estimate', 'customer_agreement', or 'other'."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        head = "\n".join((p.extract_text() or "") for p in pdf.pages[:4])
    if re.search(r"^DESCRIPTION\s+QTY\b", head, re.M):
        return "xactimate"
    first = head[:400]
    if "Reconstruction Agreement" in first or "Reconstruction Contract" in first:
        return "customer_agreement"
    if "Reconstruction Estimate" in first and "All amounts include" in head:
        return "customer_estimate"
    return "other"


def pdf_text(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def load_past_estimate(path: Path, use_ai: bool = True) -> Estimate:
    """Import one past estimate. Raises if the file isn't a priced estimate."""
    r = import_file(Path(path), use_ai=use_ai)
    if r.estimate is None:
        raise ValueError(r.message)
    return r.estimate


def import_file(path: Path, use_ai: bool = True) -> ImportResult:
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            est = Estimate.model_validate_json(path.read_text(encoding="utf-8"))
        elif suffix in (".csv", ".xlsx", ".xlsm"):
            from .spreadsheet import read_estimate_sheet
            est = read_estimate_sheet(path)
        elif suffix == ".pdf":
            kind = classify_pdf(path)
            if kind.startswith("customer_"):
                return ImportResult(path, "style", f"saved as a {kind.replace('_', ' ')} style example",
                                    text=pdf_text(path), kind=kind)
            if kind == "xactimate":
                from .xactimate_pdf import parse_xactimate
                parsed = parse_xactimate(path)
                if parsed.ok or not use_ai:
                    est = parsed.estimate
                    n = sum(len(s.items) for s in est.sections)
                    msg = f"{n} line items, {len(est.sections)} rooms ({parsed.report()})"
                    est.source_file = path.name
                    return ImportResult(path, "estimate", msg, estimate=est)
            if not use_ai:
                return ImportResult(path, "skipped", "not an Xactimate PDF; needs AI to read")
            from .estimate_pdf import ai_extract_estimate
            est = ai_extract_estimate(path)
        else:
            return ImportResult(path, "skipped", "not an estimate file")
    except Exception as e:  # keep bulk imports going
        return ImportResult(path, "error", f"{type(e).__name__}: {e}")
    est.source_file = est.source_file or path.name
    n = sum(len(s.items) for s in est.sections)
    return ImportResult(path, "estimate", f"{n} line items", estimate=est)


def iter_files(paths: list[Path]) -> Iterator[Path]:
    """Expand folders (recursively) into estimate files."""
    for p in paths:
        p = Path(p)
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in ESTIMATE_SUFFIXES
                              and not f.name.startswith(("~$", ".")))
        elif p.exists():
            yield p


def import_into_library(library, paths: list[Path], use_ai: bool = True, progress=print) -> dict[str, int]:
    """Import files and folders into the library, skipping anything already imported."""
    counts = {"estimate": 0, "style": 0, "skipped": 0, "duplicate": 0, "error": 0}
    files = list(iter_files(paths))
    for n, f in enumerate(files, 1):
        h = file_hash(f)
        if library.has_file(h):
            counts["duplicate"] += 1
            continue
        r = import_file(f, use_ai=use_ai)
        if r.status == "estimate":
            library.add(r.estimate, file_hash=h)
        elif r.status == "style":
            library.add_style_example(r.text, r.kind, f.name, file_hash=h)
        elif r.status == "skipped":
            library.mark_skipped(h, f.name, r.message)
        counts[r.status] += 1
        mark = {"estimate": "+", "style": "*", "skipped": "-", "error": "!"}[r.status]
        progress(f"[{n}/{len(files)}] {mark} {f.name}: {r.message}")
    return counts
