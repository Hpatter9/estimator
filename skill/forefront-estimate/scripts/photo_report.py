#!/usr/bin/env python3
"""Forefront photo report for the adjuster: key photos with a one-line caption each, on the Xactimate letterhead.

    python photo_report.py picks.json --photos photos/ --estimate estimate.json --out /mnt/user-data/outputs
    python photo_report.py picks.json --photos photos/ --out out --per-page 4

picks.json lists the photos in the order they should print:

    {"photos": [
        {"file": "photo_003.jpg", "caption": "Ceiling drywall removed above the tub, 4' x 6'", "room": "Bathroom"},
        {"file": "IMG_2231.jpg",  "caption": "Before loss: carpet and 3 1/4\\" baseboard", "room": "Bedroom 1"}
     ],
     "title": "Photo Report",             optional
     "date_of_loss": "2026-09-28"}        optional

Customer, address, claim number and estimate name come from estimate.json (--estimate); picks.json can set or
override any of them ("customer", "address", "claim_number", "estimate_number"). `file` is looked up in --photos,
or used as given when it is a path. Photos are rotated per EXIF and shrunk (long side 1400 px) so the PDF stays
small enough to email.

Writes "<Last Name> - Photo Report.pdf" and prints "-> <path>".
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xactimate_pdf import BOTTOM, BODY_W, CELL, CENTER_B14, FB, LM, PH, PW, TOP, Pages, St  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LONG_SIDE = 1400
CAPTION = St("caption", fontSize=10, leading=12.5)
CAPTION_SUB = St("caption_sub", fontSize=8.5, leading=10.5, textColor="#555555")


class Photo(Flowable):
    """One photo scaled to fit a box, centered."""

    def __init__(self, data: bytes, size: tuple[int, int], max_w: float, max_h: float):
        super().__init__()
        self.reader = ImageReader(io.BytesIO(data))
        w, h = size
        scale = min(max_w / w, max_h / h)
        self.w, self.h, self.box_w = w * scale, h * scale, max_w

    def wrap(self, aw, ah):
        return self.box_w, self.h

    def draw(self):
        self.canv.drawImage(self.reader, (self.box_w - self.w) / 2, 0, width=self.w, height=self.h)


def load_photo(path: Path) -> tuple[bytes, tuple[int, int]]:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((LONG_SIDE, LONG_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72, optimize=True)
    return buf.getvalue(), img.size


def last_name(customer: str) -> str:
    cust = (customer or "").strip()
    return cust.split(",")[0].strip() if "," in cust else (cust.split()[-1] if cust else "")


def safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in " -_.,&" else "_" for ch in name).strip() or "Photo"


def header_block(info: dict) -> Table:
    rows = [(k, info.get(f)) for k, f in [("Client:", "customer"), ("Property:", "address"),
                                          ("Claim Number:", "claim_number"), ("Date of Loss:", "date_of_loss"),
                                          ("Estimate:", "estimate_number"), ("Date:", "date")]]
    data = [[Paragraph(f"<b>{k}</b>", CELL), Paragraph(escape(str(v)), CELL)] for k, v in rows if v]
    t = Table(data, colWidths=[1.3 * inch, BODY_W - 1.3 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    return t


def build(picks: dict, photo_dir: Path | None, estimate: dict, out_dir: Path, per_page: int = 2) -> Path:
    info = {k: estimate.get(k) for k in ("customer", "address", "claim_number", "estimate_number")}
    info.update({k: v for k, v in picks.items() if k != "photos" and v})
    info.setdefault("date", date.today().isoformat())
    title = info.pop("title", None) or "Photo Report"

    entries = picks.get("photos") or []
    if not entries:
        raise SystemExit("picks.json has no photos")

    usable_h = TOP - BOTTOM
    cols = 1 if per_page <= 2 else 2
    rows_per_page = max(1, per_page // cols)
    cell_w = BODY_W if cols == 1 else (BODY_W - 12) / 2
    caption_h = 34
    first_page_header = 120
    cell_h = (usable_h - first_page_header) / rows_per_page - caption_h - 10

    cells = []
    for n, e in enumerate(entries, 1):
        f = Path(e["file"])
        path = f if f.is_absolute() or f.exists() or not photo_dir else photo_dir / f
        if not path.exists():
            raise SystemExit(f"photo not found: {path}")
        data, size = load_photo(path)
        room = f"{e['room']}: " if e.get("room") else ""
        sub = e.get("taken") or ""
        parts = [Photo(data, size, cell_w, cell_h), Spacer(1, 3),
                 Paragraph(f"<font name='{FB}'>Photo {n}.</font> {escape(room + (e.get('caption') or ''))}", CAPTION)]
        if sub:
            parts.append(Paragraph(escape(sub), CAPTION_SUB))
        cells.append(parts + [Spacer(1, 10)])

    story = [Paragraph(escape(title), CENTER_B14), Spacer(1, 8), header_block(info), Spacer(1, 12)]
    if cols == 1:
        story += [KeepTogether(c) for c in cells]
    else:
        for i in range(0, len(cells), 2):
            pair = cells[i:i + 2] + ([""] if len(cells[i:i + 2]) == 1 else [])
            t = Table([pair], colWidths=[cell_w + 6, cell_w + 6])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(t)

    company = json.loads((ASSETS / "company.json").read_text(encoding="utf-8"))
    d = date.fromisoformat(str(info["date"])[:10])
    pages = Pages(company, info.get("estimate_number") or title, f"{d.month}/{d.day}/{d.year}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe(last_name(info.get('customer') or '') or info.get('estimate_number') or 'Job')} - Photo Report.pdf"
    doc = BaseDocTemplate(str(path), pagesize=(PW, PH), leftMargin=LM, rightMargin=LM, topMargin=PH - TOP,
                          bottomMargin=BOTTOM, title=f"{title} - {info.get('address') or ''}".strip(" -"),
                          author=company.get("legal_name", ""))
    doc.addPageTemplates([PageTemplate("p", [Frame(LM, BOTTOM, BODY_W, TOP - BOTTOM, 0, 0, 0, 0)],
                                       onPage=pages.portrait)])
    doc.build(story)
    return path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("picks", type=Path)
    p.add_argument("--photos", type=Path, help="folder the picked files are in")
    p.add_argument("--estimate", type=Path, help="estimate.json, for client / property / claim / estimate name")
    p.add_argument("--out", type=Path, default=Path("."))
    p.add_argument("--per-page", type=int, default=2, choices=[1, 2, 4, 6])
    a = p.parse_args(argv)
    picks = json.loads(a.picks.read_text(encoding="utf-8"))
    est = json.loads(a.estimate.read_text(encoding="utf-8")) if a.estimate else {}
    path = build(picks, a.photos, est, a.out, a.per_page)
    print(f"{len(picks['photos'])} photos, {path.stat().st_size // 1024} KB")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
