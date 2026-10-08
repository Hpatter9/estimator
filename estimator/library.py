"""The estimate library: every past estimate you import, stored in SQLite.

It gives the generator two things:
  * similar past jobs (full-text search over notes, summaries and line items)
  * a price book: what you've actually charged for each line item, historically
"""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path

from .models import Estimate

DEFAULT_DB = Path("data/library.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY,
    title TEXT, loss_type TEXT, summary TEXT, source_file TEXT,
    grand_total REAL, data TEXT NOT NULL,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS line_items (
    id INTEGER PRIMARY KEY,
    estimate_id INTEGER REFERENCES estimates(id) ON DELETE CASCADE,
    section TEXT, category TEXT, selector TEXT, description TEXT,
    norm_key TEXT, quantity REAL, unit TEXT, unit_price REAL
);
CREATE INDEX IF NOT EXISTS li_norm ON line_items(norm_key, unit);
CREATE VIRTUAL TABLE IF NOT EXISTS estimates_fts USING fts5(title, loss_type, summary, body);
"""


def norm_key(description: str) -> str:
    """Normalise a line-item description so the same item from different jobs matches."""
    d = description.lower()
    d = re.sub(r"^\s*\d+\.\s*", "", d)  # leading "12. "
    d = re.sub(r"[^a-z0-9/\"' ]+", " ", d)
    return re.sub(r"\s+", " ", d).strip()


@dataclass
class PriceEntry:
    category: str
    selector: str
    description: str
    unit: str
    median_price: float
    min_price: float
    max_price: float
    times_used: int
    typical_qty: float


class Library:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # ---------- writing ----------
    def add(self, est: Estimate) -> int:
        cur = self.db.execute(
            "INSERT INTO estimates(title, loss_type, summary, source_file, grand_total, data) VALUES (?,?,?,?,?,?)",
            (est.title, est.loss_type, est.summary, est.source_file, est.grand_total, est.model_dump_json()),
        )
        eid = cur.lastrowid
        body = []
        for section, item in est.all_items():
            self.db.execute(
                "INSERT INTO line_items(estimate_id, section, category, selector, description, norm_key, quantity, unit, unit_price)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (eid, section.name, item.category, item.selector, item.description,
                 norm_key(item.description), item.quantity, item.unit.upper(), item.unit_price),
            )
            body.append(f"{section.name}: {item.description}")
        self.db.execute(
            "INSERT INTO estimates_fts(rowid, title, loss_type, summary, body) VALUES (?,?,?,?,?)",
            (eid, est.title, est.loss_type, est.summary, "\n".join(body)),
        )
        self.db.commit()
        return eid

    def delete(self, estimate_id: int) -> None:
        self.db.execute("DELETE FROM estimates WHERE id=?", (estimate_id,))
        self.db.execute("DELETE FROM estimates_fts WHERE rowid=?", (estimate_id,))
        self.db.commit()

    # ---------- reading ----------
    def list(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT id, title, loss_type, source_file, grand_total, imported_at FROM estimates ORDER BY id"
        ).fetchall()

    def get(self, estimate_id: int) -> Estimate:
        row = self.db.execute("SELECT data FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if row is None:
            raise KeyError(estimate_id)
        return Estimate.model_validate_json(row["data"])

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM estimates").fetchone()[0]

    def similar(self, text: str, limit: int = 3) -> list[Estimate]:
        """Past estimates most similar to free text (job notes, loss type, room names)."""
        words = {w for w in re.findall(r"[a-zA-Z]{3,}", text.lower())}
        if not words:
            return []
        query = " OR ".join(f'"{w}"' for w in sorted(words))
        rows = self.db.execute(
            "SELECT rowid FROM estimates_fts WHERE estimates_fts MATCH ? ORDER BY bm25(estimates_fts) LIMIT ?",
            (query, limit),
        ).fetchall()
        return [self.get(r["rowid"]) for r in rows]

    def price_book(self, min_uses: int = 1) -> list[PriceEntry]:
        """Every distinct line item you've used, with the prices you've charged."""
        rows = self.db.execute(
            "SELECT category, selector, description, norm_key, unit, unit_price, quantity FROM line_items"
            " WHERE unit_price > 0"
        ).fetchall()
        groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for r in rows:
            groups.setdefault((r["norm_key"], r["unit"]), []).append(r)
        book = []
        for (_, unit), rs in groups.items():
            if len(rs) < min_uses:
                continue
            prices = [r["unit_price"] for r in rs]
            latest = rs[-1]
            book.append(PriceEntry(
                category=latest["category"] or "", selector=latest["selector"] or "",
                description=latest["description"], unit=unit,
                median_price=round(statistics.median(prices), 2),
                min_price=min(prices), max_price=max(prices), times_used=len(rs),
                typical_qty=round(statistics.median(r["quantity"] for r in rs), 2),
            ))
        book.sort(key=lambda e: (-e.times_used, e.category, e.description))
        return book

    def lookup_price(self, description: str, unit: str) -> PriceEntry | None:
        key, unit = norm_key(description), unit.upper()
        for e in self.price_book():
            if norm_key(e.description) == key and e.unit == unit:
                return e
        return None

    def export_json(self) -> str:
        return json.dumps([json.loads(self.get(r["id"]).model_dump_json()) for r in self.list()], indent=2)
