"""Importers: turn your files into Estimate / Room objects."""
from __future__ import annotations

from pathlib import Path

from ..models import Estimate


def load_past_estimate(path: Path, use_ai: bool = True) -> Estimate:
    """Import one past estimate (Xactimate PDF, your own PDF, CSV/XLSX, or JSON)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        est = Estimate.model_validate_json(path.read_text())
    elif suffix in (".csv", ".xlsx", ".xlsm"):
        from .spreadsheet import read_estimate_sheet
        est = read_estimate_sheet(path)
    elif suffix == ".pdf":
        from .estimate_pdf import parse_estimate_pdf, ai_extract_estimate
        est = ai_extract_estimate(path) if use_ai else parse_estimate_pdf(path)
    else:
        raise ValueError(f"Don't know how to import {path.name}")
    est.source_file = est.source_file or path.name
    return est
