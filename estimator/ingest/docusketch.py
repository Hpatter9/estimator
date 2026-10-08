"""Read room measurements from DocuSketch exports.

Supported:
  * PDF reports (floor plan / measurements report) - read by Claude
  * CSV / XLSX room tables                         - read directly
  * ESX / ZIP exports                              - XML inside is read by Claude (best effort;
                                                     encrypted ESX files can't be read)
  * JSON (list of rooms)                           - read directly
Photos (JPG/PNG) aren't rooms; pass them straight to the generator as job photos.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .. import ai
from ..models import Room
from .spreadsheet import fill_derived, read_room_sheet

ROOMS_SCHEMA = ai.obj({"rooms": {"type": "array", "items": ai.ROOM_SCHEMA}})

ROOMS_SYSTEM = """You read measurement reports from DocuSketch (360-camera floor plans) and list every room.
For each room give length/width/height in decimal feet, and floor SF, ceiling SF, wall SF and floor
perimeter LF exactly as printed. Convert feet-inches like 12' 6" to 12.5. Use null when a value isn't
shown. Put anything useful that isn't a number (openings, ceiling type, flooring type, level) in notes."""

MAX_XML_CHARS = 400_000


def load_rooms(path: Path) -> list[Room]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".csv", ".xlsx", ".xlsm"):
        return read_room_sheet(path)
    if suffix == ".json":
        data = json.loads(path.read_text())
        rooms = data.get("rooms", data) if isinstance(data, dict) else data
        return [fill_derived(Room.model_validate(r)) for r in rooms]
    if suffix == ".pdf":
        content = [ai.file_block(path), {"type": "text", "text": "List every room and its measurements."}]
    elif suffix in (".esx", ".zip") and zipfile.is_zipfile(path):
        content = [{"type": "text", "text": _zip_xml(path)}]
    else:
        raise ValueError(f"Don't know how to read rooms from {path.name}")
    data = ai.structured(ROOMS_SYSTEM, content, ROOMS_SCHEMA, effort="medium")
    return [fill_derived(Room.model_validate(r)) for r in data["rooms"]]


def _zip_xml(path: Path) -> str:
    parts = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lower().endswith((".xml", ".zipxml", ".json")):
                try:
                    parts.append(f"--- {name} ---\n" + z.read(name).decode("utf-8", errors="replace"))
                except RuntimeError as e:  # encrypted member
                    raise ValueError(f"{path.name} is encrypted; export a PDF or CSV from DocuSketch instead") from e
    text = "\n".join(parts)
    if not text:
        raise ValueError(f"No readable XML found in {path.name}; export a PDF or CSV from DocuSketch instead")
    if len(text) > MAX_XML_CHARS:
        raise ValueError(f"{path.name} is too large to read in one pass; export the measurements PDF instead")
    return text
