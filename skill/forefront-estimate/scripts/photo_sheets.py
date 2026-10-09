#!/usr/bin/env python3
"""Make numbered contact sheets from job photos so you can look through them quickly.

    python photo_sheets.py photos.zip --out /tmp/photos        # a zip downloaded from DocuSketch
    python photo_sheets.py photo_folder/ img1.jpg img2.png --out /tmp/photos

Writes sheet_01.jpg, sheet_02.jpg ... (12 photos each, numbered, with file names) and a full-size
copy of every photo as photo_###.jpg (long side 1600 px) for a closer look at anything on a sheet.
Look at the sheets first; open individual photos only where you need detail.
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
THUMB, COLS, PER_SHEET = 420, 4, 12


def load(paths: list[Path]) -> list[tuple[str, Image.Image]]:
    out = []
    for p in paths:
        if p.is_dir():
            out += load(sorted(f for f in p.rglob("*") if f.is_file()))
        elif p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                for name in sorted(z.namelist()):
                    if Path(name).suffix.lower() in EXTS and not Path(name).name.startswith("."):
                        out.append(_open(Path(name).name, z.read(name)))
        elif p.suffix.lower() in EXTS:
            out.append(_open(p.name, p.read_bytes()))
    return [o for o in out if o[1] is not None]


def _open(name: str, data: bytes):
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        return name, im
    except Exception as e:  # unreadable file - skip it but say so
        print(f"! skipped {name}: {e}", file=sys.stderr)
        return name, None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=Path("photos"))
    a = p.parse_args(argv)
    photos = load(a.inputs)
    if not photos:
        print("No photos found (supported: jpg, png, webp, bmp, tif; zip files and folders).")
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    for n, (name, im) in enumerate(photos, 1):
        big = im.copy()
        big.thumbnail((1600, 1600))
        big.save(a.out / f"photo_{n:03d}.jpg", quality=85)
    rows = (PER_SHEET + COLS - 1) // COLS
    label_h = 22
    for s in range(0, len(photos), PER_SHEET):
        chunk = photos[s:s + PER_SHEET]
        sheet = Image.new("RGB", (COLS * THUMB, rows * (THUMB + label_h)), "white")
        draw = ImageDraw.Draw(sheet)
        for k, (name, im) in enumerate(chunk):
            t = im.copy()
            t.thumbnail((THUMB - 8, THUMB - 8))
            x, y = (k % COLS) * THUMB, (k // COLS) * (THUMB + label_h)
            sheet.paste(t, (x + (THUMB - t.width) // 2, y + (THUMB - t.height) // 2))
            draw.rectangle([x, y + THUMB, x + THUMB, y + THUMB + label_h], fill=(22, 50, 74))
            draw.text((x + 6, y + THUMB + 5), f"#{s + k + 1}  {name[:48]}", fill="white")
        sheet.save(a.out / f"sheet_{s // PER_SHEET + 1:02d}.jpg", quality=80)
    n_sheets = (len(photos) + PER_SHEET - 1) // PER_SHEET
    print(f"{len(photos)} photos -> {n_sheets} contact sheets in {a.out} (sheet_01.jpg ...); "
          f"full-size copies are photo_001.jpg ... photo_{len(photos):03d}.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
