#!/usr/bin/env python3
"""Room measurements from a Keystone Scan file (room-scan-<job>-<date>.json, measured with an iPhone's LiDAR) - no
AI, no extra packages.

    python read_scan.py room-scan-3212-20261125-1410.json
    python read_scan.py room-scan-3212-20261125-1410.json --height "Kitchen=9" --json rooms.json

Prints one line per room: ceiling height, floor SF, wall SF (doors, windows and openings taken out), floor perimeter
LF (doorways and open walls taken out: that's the baseboard run) and ceiling perimeter LF, then each room's doors,
windows, openings and the fixtures the scanner recognised. The numbers come straight from the scan, so they're not
read off a picture. --height replaces a room's measured ceiling height (wall SF is worked out again from it).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ScanRoom:
    name: str
    level: str
    height_ft: float
    floor_sf: float
    ceiling_perimeter_lf: float
    floor_perimeter_lf: float
    wall_sf: float
    openings_sf: float = 0.0
    openings: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    walls_lf: list[float] = field(default_factory=list)


def _ft_in(v: float) -> str:
    total = round(v * 12)
    return f"{total // 12}' {total % 12}\""


def read_scan(path: Path, heights: dict[str, float] | None = None) -> list[ScanRoom]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("app") != "Keystone Scan":
        raise SystemExit(f"{path} isn't a Keystone Scan file.")
    heights = {k.lower(): v for k, v in (heights or {}).items()}
    rooms: list[ScanRoom] = []
    for r in data.get("rooms", []):
        name = r.get("name") or f"Room {len(rooms) + 1}"
        walls = r.get("walls", [])
        doors, windows, holes = r.get("doors", []), r.get("windows", []), r.get("openings", [])
        ceiling_lf = sum(w.get("lengthFt", 0) for w in walls) or r.get("perimeterLF", 0)
        height = heights.get(name.lower(), r.get("ceilingHeightFt") or 8.0)
        openings_sf = sum(o.get("widthFt", 0) * o.get("heightFt", 0) for o in doors + windows + holes)
        # A wall's area from its own height, unless the height was given: then every wall is that tall.
        gross = sum(w.get("lengthFt", 0) * (height if name.lower() in heights else w.get("heightFt", height)) for w in walls)
        # Baseboard runs along the floor, so doorways and open walls (not windows) come out of it.
        floor_lf = max(0.0, ceiling_lf - sum(o.get("widthFt", 0) for o in doors + holes))
        rooms.append(ScanRoom(
            name=name,
            level=r.get("level", ""),
            height_ft=round(height, 2),
            floor_sf=round(r.get("floorAreaSF", 0.0), 2),
            ceiling_perimeter_lf=round(ceiling_lf, 2),
            floor_perimeter_lf=round(floor_lf, 2),
            wall_sf=round(max(0.0, gross - openings_sf), 2),
            openings_sf=round(openings_sf, 2),
            openings=[f"{o['kind']} {_ft_in(o.get('widthFt', 0))} x {_ft_in(o.get('heightFt', 0))}" for o in doors + windows + holes if "kind" in o],
            fixtures=[f"{x.get('kind', '?')} {_ft_in(x.get('widthFt', 0))} x {_ft_in(x.get('depthFt', 0))}" for x in r.get("objects", [])],
            walls_lf=[round(w.get("lengthFt", 0), 2) for w in walls],
        ))
    # Two rooms with the same name get (1), (2), as the ESX reader did.
    counts: dict[str, int] = {}
    for r in rooms:
        counts[r.name] = counts.get(r.name, 0) + 1
    seen: dict[str, int] = {}
    for r in rooms:
        if counts[r.name] > 1:
            seen[r.name] = seen.get(r.name, 0) + 1
            r.name = f"{r.name} ({seen[r.name]})"
    return rooms


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("scan", type=Path)
    a.add_argument("--height", action="append", default=[], help='a room\'s real ceiling height: "Kitchen=9"')
    a.add_argument("--json", type=Path, help="also save the rooms as JSON")
    args = a.parse_args(argv)
    heights: dict[str, float] = {}
    for h in args.height:
        name, _, ft = h.rpartition("=")
        heights[name.strip()] = float(ft)
    rooms = read_scan(args.scan, heights)
    for name in heights:
        if not any(r.name.lower() == name.lower() for r in rooms):
            print(f"! no room named {name!r}", file=sys.stderr)
    data = json.loads(args.scan.read_text(encoding="utf-8"))
    print(f"Keystone Scan of #{data.get('jobNumber', '?')} {data.get('jobName', '')} ({len(rooms)} rooms, iPhone LiDAR)")
    print(f"{'Room':<26} {'Ht ft':>6} {'Floor SF':>9} {'Wall SF':>8} {'Floor LF':>9} {'Ceil LF':>8}")
    for r in rooms:
        print(f"{r.name[:26]:<26} {r.height_ft:>6.2f} {r.floor_sf:>9.2f} {r.wall_sf:>8.2f} {r.floor_perimeter_lf:>9.2f} {r.ceiling_perimeter_lf:>8.2f}")
    for r in rooms:
        extra = r.openings + [f"fixture: {f}" for f in r.fixtures]
        if extra:
            print(f"  {r.name}: " + "; ".join(extra))
    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in rooms], indent=2), encoding="utf-8")
        print(f"\nSaved {len(rooms)} rooms to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
