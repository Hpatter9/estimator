"""Your own estimate template: estimator/templates/company_estimate.html.j2 (edit freely).

Writes HTML, and also a PDF when a Chromium/Chrome browser is installed (it prints the HTML).
Drop more *.html.j2 files into the templates folder and pass template="name.html.j2" to use them.
"""
from __future__ import annotations

import base64
import mimetypes
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import Company
from ..models import Estimate

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
CHROMES = ["chromium", "chromium-browser", "google-chrome", "chrome", "/opt/pw-browsers/chromium"]


def render(est: Estimate, company: Company, template: str = "company_estimate.html.j2") -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["money"] = lambda v: f"${v:,.2f}"
    logo = ""
    if company.logo_path and Path(company.logo_path).exists():
        mime = mimetypes.guess_type(company.logo_path)[0] or "image/png"
        logo = f"data:{mime};base64," + base64.b64encode(Path(company.logo_path).read_bytes()).decode()
    return env.get_template(template).render(est=est, company=company, logo=logo)


def write(est: Estimate, html_path: Path, company: Company, template: str = "company_estimate.html.j2") -> list[Path]:
    html_path.write_text(render(est, company, template))
    out = [html_path]
    pdf = html_to_pdf(html_path)
    if pdf:
        out.append(pdf)
    return out


def html_to_pdf(html_path: Path) -> Path | None:
    exe = next((shutil.which(c) or (c if Path(c).is_file() else None) for c in CHROMES
                if shutil.which(c) or Path(c).is_file()), None)
    if not exe:
        return None
    pdf_path = html_path.with_suffix(".pdf")
    try:
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                       check=True, capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    return pdf_path if pdf_path.exists() else None
