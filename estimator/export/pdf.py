"""Print an HTML file to PDF with a locally installed Chrome, Edge or Chromium."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = [
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge",
    "/opt/pw-browsers/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str | None:
    if os.environ.get("ESTIMATOR_BROWSER"):
        return os.environ["ESTIMATOR_BROWSER"]
    for c in CANDIDATES:
        found = shutil.which(c) or (c if Path(c).is_file() else None)
        if found:
            return found
    return None


def html_to_pdf(html_path: Path) -> Path | None:
    exe = find_browser()
    if not exe:
        return None
    pdf_path = html_path.with_suffix(".pdf")
    try:
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    return pdf_path if pdf_path.exists() else None
