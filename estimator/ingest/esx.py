"""Read room measurements straight from a DocuSketch / Xactimate .ESX file (no AI, no cost).

An ESX is a zip with:
  * <number>.XML     - the sketch: levels, rooms, walls, doors/windows (readable)
  * XACTDOC.ZIPXML   - the Xactimate estimate data (encrypted; not used)

Sketch units are 1/127 inch (1 ft = 1524). DocuSketch exports every room at its default 8' ceiling;
set real heights with Room.set_height() (the CLI's --height, or the room table in the app) and wall SF
is recomputed - checked against a finished Xactimate: floor SF and perimeter exact, walls within 1%. Rooms are polygons of wall centerlines; we move each
wall in by half its thickness to get interior dimensions, then compute the numbers Xactimate shows:
  SF Floor / Ceiling  - interior area
  LF Ceil. Perimeter  - interior perimeter
  LF Floor Perimeter  - ceiling perimeter minus openings that go to the floor (doors, missing walls)
  SF Walls            - ceiling perimeter x height minus all openings (doors, windows, missing walls)
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Room

UNITS_PER_FT = 1524.0


@dataclass
class SketchRoom:
    name: str
    level: str
    height_ft: float
    floor_sf: float
    ceiling_perimeter_lf: float
    floor_perimeter_lf: float
    wall_sf: float
    openings_sf: float = 0.0
    openings: list[str] = field(default_factory=list)

    def to_room(self) -> Room:
        notes = f"Level: {self.level}"
        if self.openings:
            notes += "; openings: " + ", ".join(self.openings)
        return Room(name=self.name, height_ft=self.height_ft, floor_sf=self.floor_sf, ceiling_sf=self.floor_sf,
                    wall_sf=self.wall_sf, perimeter_lf=self.floor_perimeter_lf,
                    ceiling_perimeter_lf=self.ceiling_perimeter_lf, openings_sf=self.openings_sf, notes=notes)


def _sketch_xml(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lower().endswith(".xml"):
                data = z.read(name)
                if b"<SKETCHDOCUMENT" in data[:4000] or b"SKETCH_FILES" in data[:200]:
                    return ET.fromstring(data)
    raise ValueError(f"{Path(path).name}: no sketch found inside the ESX")


def _num_id(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def _loop(edges: list[tuple[int, int]]) -> list[int]:
    """Chain wall edges (vertex pairs) into the longest closed loop of vertex ids."""
    remaining = edges[:]
    best: list[int] = []
    while remaining:
        a, b = remaining.pop(0)
        loop = [a, b]
        progress = True
        while progress and loop[-1] != loop[0]:
            progress = False
            for i, (x, y) in enumerate(remaining):
                if x == loop[-1] or y == loop[-1]:
                    loop.append(y if x == loop[-1] else x)
                    remaining.pop(i)
                    progress = True
                    break
        if loop[-1] == loop[0] and len(loop) - 1 > len(best):
            best = loop[:-1]
    return best


def _area(pts):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])) / 2


def _perimeter(pts):
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:] + pts[:1]))


def _inset(pts, offsets):
    """Move edge i (pts[i] -> pts[i+1]) inward by offsets[i]; return the new corner points."""
    n = len(pts)
    sign = 1 if _area(pts) > 0 else -1  # inward normal is to the left of a CCW polygon
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length * sign, dx / length * sign
        d = offsets[i]
        lines.append(((x1 + nx * d, y1 + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p, r), (q, s) = lines[i - 1], lines[i]
        cross = r[0] * s[1] - r[1] * s[0]
        if abs(cross) < 1e-9:  # parallel neighbours: keep the shifted point
            out.append(q)
            continue
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / cross
        out.append((p[0] + r[0] * t, p[1] + r[1] * t))
    return out


def read_esx(path: Path) -> list[SketchRoom]:
    root = _sketch_xml(Path(path))
    nums = [float(v) for v in root.find(".//COORDINATE3").text.split()]
    coords = [tuple(nums[i:i + 3]) for i in range(0, len(nums) - 2, 3)]

    vertex_coord = {_num_id(v.get("id")): int(v.get("vertex")) for v in root.iter("SKETCHLEVELVERTEX")}
    walls = {}
    wall_by_json = {}
    for w in root.iter("SKETCHWALL"):
        a, b = (int(x) for x in w.get("vertexIDs").split())
        rec = {"v": (a, b), "t": float(w.get("thickness", 0)), "rooms": [int(x) for x in w.get("roomIDs", "").split()]}
        walls[_num_id(w.get("id"))] = rec
        wall_by_json[w.get("jsonId")] = rec

    # openings per room: (width_ft, height_ft, to_floor, label)
    openings: dict[int, list[tuple[float, float, bool]]] = {}
    levels = {}
    for level in root.iter("SKETCHLEVEL"):
        levels[level.get("id")] = float(level.get("floorElevation", 0))
    for o in root.iter("SKETCHWALLOPENING"):
        wall = wall_by_json.get(o.get("wallId"))
        if not wall:
            continue
        pts = [coords[int(i)] for i in o.get("coordIndex").split()]
        zs = [p[2] for p in pts]
        width = max(math.dist(p[:2], q[:2]) for p in pts for q in pts) / UNITS_PER_FT
        height = (max(zs) - min(zs)) / UNITS_PER_FT
        for rid in wall["rooms"]:
            if rid:
                openings.setdefault(rid, []).append((width, height, min(zs)))

    rooms: list[SketchRoom] = []
    for level in root.iter("SKETCHLEVEL"):
        floor_z = float(level.get("floorElevation", 0))
        for r in level.iter("SKETCHROOM"):
            rid = _num_id(r.get("id"))
            label = r.find(".//SKETCHCDATACHILD")
            name = (label.text or "").strip() if label is not None else r.get("jsonId", "Room")
            height = float(r.get("ceilingHeight", 0)) / UNITS_PER_FT
            wall_ids = [int(x) for x in r.get("wallIDs", "").split()]
            edges = [walls[w]["v"] for w in wall_ids if w in walls]
            loop = _loop(edges)
            if len(loop) < 3:
                continue
            pts = [coords[vertex_coord[v]][:2] for v in loop]
            thick = {}
            for w in wall_ids:
                if w in walls:
                    a, b = walls[w]["v"]
                    thick[frozenset((a, b))] = walls[w]["t"]
            offsets = [thick.get(frozenset((loop[i], loop[(i + 1) % len(loop)])), 0) / 2 for i in range(len(loop))]
            inner = _inset(pts, offsets)
            area_sf = abs(_area(inner)) / UNITS_PER_FT ** 2
            if area_sf <= 0 or area_sf > abs(_area(pts)) / UNITS_PER_FT ** 2 * 1.01:
                inner = pts  # inset went wrong (odd shape) - fall back to centerlines
                area_sf = abs(_area(pts)) / UNITS_PER_FT ** 2
            ceil_perim = _perimeter(inner) / UNITS_PER_FT
            ops = openings.get(rid, [])
            to_floor = [w for w, h, z in ops if abs(z - floor_z) < 30]
            floor_perim = max(ceil_perim - sum(to_floor), 0)
            openings_sf = sum(w * h for w, h, _ in ops)
            wall_sf = max(ceil_perim * height - openings_sf, 0)
            labels = [f"{'door/opening' if abs(z - floor_z) < 30 else 'window'} {w:.1f}' x {h:.1f}'" for w, h, z in ops]
            rooms.append(SketchRoom(name, level.get("name", ""), round(height, 2), round(area_sf, 2),
                                    round(ceil_perim, 2), round(floor_perim, 2), round(wall_sf, 2), round(openings_sf, 2), labels))
    return rooms


def load_esx_rooms(path: Path) -> list[Room]:
    return [r.to_room() for r in read_esx(path)]
