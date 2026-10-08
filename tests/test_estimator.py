from pathlib import Path

import pytest

from estimator import generate as gen_mod
from estimator.config import Company
from estimator.export import FORMATS, export
from estimator.ingest import load_past_estimate
from estimator.ingest.spreadsheet import read_room_sheet
from estimator.library import Library
from estimator.models import Estimate, LineItem, Section

EX = Path(__file__).resolve().parent.parent / "examples"

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
        "sections": [{"name": "Kitchen", "option": "", "items": [
            {"category": "DRY", "selector": "1/2", "description": "1/2 drywall", "quantity": 92, "unit": "sf",
             "price_book_match": '1/2" drywall - hung, taped, floated, ready for paint',
             "suggested_unit_price": 9.99, "note": ""},
            {"category": "FCV", "selector": "LVP", "description": "Vinyl plank flooring", "quantity": 132, "unit": "SF",
             "price_book_match": "", "suggested_unit_price": 6.5, "note": ""},
        ]}],
    }
    monkeypatch.setattr(gen_mod.ai, "structured", lambda *a, **k: fake)
    rooms = read_room_sheet(EX / "docusketch_rooms_sample.csv")
    est, qs = gen_mod.generate_estimate(lib, "water kitchen", rooms, customer_scope=False)
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
