from pathlib import Path

import pytest

from estimator import generate as gen_mod
from estimator.config import Company
from estimator.export import FORMATS, export
from estimator.ingest import load_past_estimate
from estimator.ingest.estimate_pdf import parse_estimate_text
from estimator.ingest.spreadsheet import read_room_sheet
from estimator.library import Library
from estimator.models import Estimate, LineItem, Section

EX = Path(__file__).resolve().parent.parent / "examples"

XACT_TEXT = """Kitchen
Height: 8'
384.00 SF Walls 132.00 SF Ceiling
DESCRIPTION QUANTITY UNIT PRICE TAX O&P RCV
1. Tear out wet drywall, cleanup, bag for disposal 92.00 SF 1.45 0.00 26.68 160.08
2. 1/2" drywall - hung, taped, floated, ready for paint 92.00 SF 2.88 4.12 53.82 322.90
Totals: Kitchen 4.12 80.50 482.98
Hallway
Height: 8'
3. Baseboard - 3 1/4" 38.00 LF 4.10 1.20 31.40 188.40
"""


def test_regex_parser_reads_rooms_and_items():
    est = parse_estimate_text(XACT_TEXT)
    assert [s.name for s in est.sections] == ["Kitchen", "Hallway"]
    first = est.sections[0].items[1]
    assert first.description.startswith('1/2" drywall')
    assert (first.quantity, first.unit, first.unit_price, first.tax) == (92.0, "SF", 2.88, 4.12)


def test_rooms_from_csv_get_derived_areas():
    rooms = read_room_sheet(EX / "docusketch_rooms_sample.csv")
    k = rooms[0]
    assert (k.floor_sf, k.perimeter_lf, k.wall_sf) == (132.0, 46.0, 368.0)


@pytest.fixture
def lib(tmp_path):
    lib = Library(tmp_path / "lib.db")
    est = load_past_estimate(EX / "past_estimate_sample.csv")
    est.loss_type, est.summary = "water", "Cat 2 water loss in kitchen, flood cut and drying"
    lib.add(est)
    return lib


def test_library_similar_and_price_book(lib):
    assert lib.similar("dishwasher water leak kitchen")[0].loss_type == "water"
    entry = lib.lookup_price('1/2" drywall - hung, taped, floated, ready for paint', "sf")
    assert entry and entry.median_price == 2.88


def test_generate_uses_history_prices(lib, monkeypatch):
    fake = {
        "title": "Smith water loss", "loss_type": "water", "summary": "s", "questions": ["Pad wet?"],
        "sections": [{"name": "Kitchen", "items": [
            {"category": "DRY", "selector": "1/2", "description": "1/2 drywall", "quantity": 92, "unit": "sf",
             "price_book_match": '1/2" drywall - hung, taped, floated, ready for paint',
             "suggested_unit_price": 9.99, "note": ""},
            {"category": "FCV", "selector": "LVP", "description": "Vinyl plank flooring", "quantity": 132, "unit": "SF",
             "price_book_match": "", "suggested_unit_price": 6.5, "note": ""},
        ]}],
    }
    monkeypatch.setattr(gen_mod.ai, "structured", lambda *a, **k: fake)
    rooms = read_room_sheet(EX / "docusketch_rooms_sample.csv")
    est, qs = gen_mod.generate_estimate(lib, "water kitchen", rooms)
    a, b = est.sections[0].items
    assert (a.unit_price, a.price_source) == (2.88, "history")
    assert (b.unit_price, b.price_source) == (6.5, "ai")
    assert est.sections[0].room.name == "Kitchen" and qs == ["Pad wet?"]


def test_totals():
    est = Estimate(sections=[Section(name="A", items=[LineItem(description="x", quantity=10, unit_price=2, tax=1)])],
                   overhead_pct=10, profit_pct=10, tax_pct=5)
    assert (est.line_item_total, est.sales_tax, est.overhead, est.grand_total) == (20, 2.0, 2.0, 26.0)


@pytest.mark.parametrize("fmt", list(FORMATS))
def test_exports(fmt, tmp_path):
    est = load_past_estimate(EX / "past_estimate_sample.csv")
    paths = export(est, fmt, tmp_path, Company())
    assert paths and all(p.exists() and p.stat().st_size > 0 for p in paths)
