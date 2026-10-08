"""Exporters: one Estimate in, many formats out."""
from __future__ import annotations

from pathlib import Path

from ..config import Company
from ..models import Estimate

FORMATS = {
    "xactimate": "Xactimate-style PDF (room-by-room line items, recap, O&P summary)",
    "company": "Your company template (HTML, plus PDF when Chromium is available)",
    "excel": "Excel workbook",
    "csv": "CSV of line items",
    "json": "JSON (re-importable / editable)",
}


def export(est: Estimate, fmt: str, out_dir: Path, company: Company) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe(est.title or "estimate")
    if fmt == "xactimate":
        from .xactimate_style import write_pdf
        return [write_pdf(est, out_dir / f"{stem} - xactimate style.pdf", company)]
    if fmt == "company":
        from .company_template import write
        return write(est, out_dir / f"{stem}.html", company)
    if fmt == "excel":
        from .tables import write_xlsx
        return [write_xlsx(est, out_dir / f"{stem}.xlsx")]
    if fmt == "csv":
        from .tables import write_csv
        return [write_csv(est, out_dir / f"{stem}.csv")]
    if fmt == "json":
        p = out_dir / f"{stem}.json"
        p.write_text(est.model_dump_json(indent=2))
        return [p]
    raise ValueError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "estimate"
