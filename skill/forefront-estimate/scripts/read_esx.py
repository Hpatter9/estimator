#!/usr/bin/env python3
"""Room measurements from a DocuSketch .ESX file - no AI, no extra packages. (Generated from
estimator/ingest/esx.py; edit that file and run `py -m estimator build-skill`, not this one.)

    python read_esx.py job.ESX                         # every room, 8' ceilings (DocuSketch default)
    python read_esx.py job.ESX --height "Kitchen=10" --height "Bathroom #2=9" --default-height 8.75
    python read_esx.py job.ESX --json rooms.json       # also save for render.py / your notes

Prints one line per room: floor SF, wall SF (minus doors/windows), floor perimeter LF (minus
doorways), ceiling perimeter LF and height - the same numbers Xactimate shows for the sketch.
Checked against a finished Xactimate: floor SF and perimeter exact, walls within 1%.

DocuSketch exports every room at an 8' ceiling. Real heights change wall SF:
    wall_sf = ceiling_perimeter_lf x height - openings_sf
Sketch filler (voids, wall cavities, unnamed spaces under 10 SF) is dropped; duplicate names get (1), (2).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

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


def clean(rooms: list[SketchRoom], min_sf: float = 10.0) -> list[SketchRoom]:
    kept = [r for r in rooms if r.name.lower() != "void"
            and not (r.name.lower().startswith("unknown room") and r.floor_sf < min_sf) and r.floor_sf >= 1.0]
    counts: dict[str, int] = {}
    for r in kept:
        counts[r.name] = counts.get(r.name, 0) + 1
    seen: dict[str, int] = {}
    for r in kept:
        if counts[r.name] > 1:
            seen[r.name] = seen.get(r.name, 0) + 1
            r.name = f"{r.name} ({seen[r.name]})"
    return kept


def set_height(room: SketchRoom, height_ft: float) -> SketchRoom:
    room.height_ft = height_ft
    room.wall_sf = round(max(room.ceiling_perimeter_lf * height_ft - room.openings_sf, 0), 2)
    return room


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("esx", type=Path)
    p.add_argument("--height", action="append", default=[], metavar="ROOM=FEET")
    p.add_argument("--default-height", type=float)
    p.add_argument("--json", type=Path, help="write the rooms to this JSON file")
    p.add_argument("--all", action="store_true", help="keep voids and tiny unnamed spaces")
    a = p.parse_args(argv)

    rooms = read_esx(a.esx)
    if not a.all:
        rooms = clean(rooms)
    heights = {k.strip().lower(): float(v) for k, _, v in (h.partition("=") for h in a.height)}
    for r in rooms:
        h = heights.pop(r.name.lower(), a.default_height)
        if h:
            set_height(r, h)
    for name in heights:
        print(f"! no room named {name!r}", file=sys.stderr)

    print(f"{'Level':<10} {'Room':<26} {'Ht ft':>6} {'Floor SF':>9} {'Wall SF':>8} {'Floor LF':>9} {'Ceil LF':>8}")
    for r in rooms:
        print(f"{r.level[:10]:<10} {r.name[:26]:<26} {r.height_ft:>6.2f} {r.floor_sf:>9.2f} {r.wall_sf:>8.2f} "
              f"{r.floor_perimeter_lf:>9.2f} {r.ceiling_perimeter_lf:>8.2f}")
    if all(r.height_ft == 8 for r in rooms) and not a.height and not a.default_height:
        print("\nAll ceilings are DocuSketch's default 8'. Ask for real heights; they change wall SF.")
    if a.json:
        a.json.write_text(json.dumps([asdict(r) for r in rooms], indent=2), encoding="utf-8")
        print(f"\nSaved {len(rooms)} rooms to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
