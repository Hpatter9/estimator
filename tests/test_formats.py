"""Tests for the ESX reader, the Xactimate PDF reader, and the customer Estimate / Agreement."""
import zipfile
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from estimator import customer as customer_mod
from estimator.config import load_company
from estimator.export.customer_docs import build_scopes, payments, render
from estimator.ingest import classify_pdf, import_into_library
from estimator.ingest.docusketch import clean_rooms
from estimator.ingest.esx import read_esx
from estimator.ingest.xactimate_pdf import parse_xactimate
from estimator.library import Library
from estimator.models import Estimate, LineItem, Room, Section

FT = 1524


def make_esx(path: Path, thickness: int = 0) -> Path:
    """One 12' x 10' room, 8' ceiling, a 3' x 6'8" door and a 3' x 4' window."""
    z0 = 100 * FT
    corners = [(0, 0), (12 * FT, 0), (12 * FT, 10 * FT), (0, 10 * FT)]
    coords = [(0, 0, 0)] + [(x, y, z0) for x, y in corners]
    door = [(1 * FT, 0, z0), (4 * FT, 0, z0), (4 * FT, 0, z0 + 80 * 127), (1 * FT, 0, z0 + 80 * 127)]
    window = [(12 * FT, 3 * FT, z0 + 3 * FT), (12 * FT, 6 * FT, z0 + 3 * FT),
              (12 * FT, 6 * FT, z0 + 7 * FT), (12 * FT, 3 * FT, z0 + 7 * FT)]
    coords += door + window
    flat = " ".join(f"{x} {y} {z}" for x, y, z in coords)
    verts = "".join(f'<SKETCHLEVELVERTEX id="SKT{10 + i}" vertex="{i}" wallIDs="" />' for i in range(1, 5))
    walls = "".join(
        f'<SKETCHWALL id="SKT{20 + i}" vertexIDs="{10 + i} {10 + i % 4 + 1}" thickness="{thickness}" '
        f'jsonId="w{i}" roomIDs="30 0" />' for i in range(1, 5))
    xml = f"""<FIF><SKETCH_FILES><SKETCHDOCUMENT id="SKT1">
      <SKETCHLEVEL floorElevation="{z0}" id="SKT2" name="1st Floor">{verts}{walls}
        <SKETCHROOM id="SKT30" ceilingHeight="{8 * FT}" wallIDs="21 22 23 24" jsonId="room1">
          <SKETCHLABEL id="SKT31"><SKETCHCDATACHILD>Kitchen</SKETCHCDATACHILD></SKETCHLABEL></SKETCHROOM>
      </SKETCHLEVEL>
      <SKETCHWALLOPENING coordIndex="5 6 7 8" wallId="w1" id="SKT40" type="1" />
      <SKETCHWALLOPENING coordIndex="9 10 11 12" wallId="w2" id="SKT41" type="2" />
      <COORDINATE3>{flat}</COORDINATE3></SKETCHDOCUMENT></SKETCH_FILES></FIF>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("123.XML", xml)
        z.writestr("XACTDOC.ZIPXML", b"\x00encrypted")
    return path


def test_esx_room_measurements(tmp_path):
    (room,) = read_esx(make_esx(tmp_path / "job.esx"))
    assert room.name == "Kitchen" and room.level == "1st Floor" and room.height_ft == 8
    assert room.floor_sf == 120 and room.ceiling_perimeter_lf == 44
    assert room.floor_perimeter_lf == 41  # door goes to the floor, window doesn't
    assert room.wall_sf == pytest.approx(44 * 8 - 3 * 80 / 12 - 3 * 4, abs=0.01)


def test_esx_uses_interior_faces(tmp_path):
    (room,) = read_esx(make_esx(tmp_path / "job.esx", thickness=508))  # 4" walls -> 2" in from centerline
    assert room.floor_sf == pytest.approx((12 - 4 / 12) * (10 - 4 / 12), abs=0.01)


def test_clean_rooms_drops_voids_and_numbers_duplicates():
    rooms = [Room(name="Void", floor_sf=20), Room(name="Unknown Room_3", floor_sf=2),
             Room(name="Great Room", floor_sf=50), Room(name="Great Room", floor_sf=60)]
    assert [r.name for r in clean_rooms(rooms)] == ["Great Room (1)", "Great Room (2)"]


def make_xactimate_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 760

    def line(text, font="Times-Roman", size=9, gap=16):
        nonlocal y
        y -= gap
        c.setFont(font, size)
        c.drawString(36, y, text)

    line("Client: Jane Doe", gap=0)
    line("Property: 1 Main St")
    line("Denver, CO 80211", gap=12)
    line("Estimate: DOE_1_REC")
    line("Kitchen Height: 7' 9\"", "Times-Bold", 10, gap=30)
    line("362.91 SF Walls 153.36 SF Ceiling", size=10, gap=14)
    line("153.36 SF Floor 46.29 LF Floor Perimeter", size=10, gap=14)
    line("DESCRIPTION QTY REMOVE REPLACE TAX O&P TOTAL", "Times-Bold")
    line("Drywall", "Times-BoldItalic")
    line("1. 1/2\" drywall - hung, taped, ready 187.00 SF 0.00 2.72 0.00 101.72 610.36")
    line("for texture", gap=10)
    line("Additional labor for a non-factory edge.")
    line("Plumbing", "Times-BoldItalic")
    line("2. R&R Angle stop valve 2.00 EA 7.05 60.97 0.00 27.20 163.24")
    line("Totals: Kitchen 0.00 128.92 773.60", gap=22)
    c.save()
    return path


def test_xactimate_pdf_reader(tmp_path):
    r = parse_xactimate(make_xactimate_pdf(tmp_path / "x.pdf"))
    assert r.ok, r.report()
    est = r.estimate
    assert (est.customer, est.title, est.address) == ("Jane Doe", "DOE_1_REC", "1 Main St, Denver, CO 80211")
    (kitchen,) = est.sections
    assert kitchen.room.wall_sf == 362.91 and kitchen.room.height_ft == 7.75
    a, b = kitchen.items
    assert a.description == '1/2" drywall - hung, taped, ready for texture' and a.group == "Drywall"
    assert a.note == "Additional labor for a non-factory edge." and a.unit_price == 2.72
    assert b.unit_price == 68.02 and b.group == "Plumbing"
    assert classify_pdf(tmp_path / "x.pdf") == "xactimate"


def test_folder_import_skips_repeats(tmp_path):
    folder = tmp_path / "estimates" / "2026"
    folder.mkdir(parents=True)
    make_xactimate_pdf(folder / "a.pdf")
    lib = Library(tmp_path / "lib.db")
    first = import_into_library(lib, [tmp_path / "estimates"], use_ai=False, progress=lambda m: None)
    again = import_into_library(lib, [tmp_path / "estimates"], use_ai=False, progress=lambda m: None)
    assert first["estimate"] == 1 and again["duplicate"] == 1 and lib.count() == 1


@pytest.mark.parametrize("total,expected", [
    (25967.44, [12983.72, 10386.98, 2596.74]),  # totals from real estimates
    (18808.61, [9404.31, 7523.44, 1880.86]),
    (16895.57, [8447.79, 6758.23, 1689.55]),
])
def test_billing_matches_your_estimates(total, expected):
    assert payments(total, [50, 40, 10]) == expected


def sample_estimate() -> Estimate:
    return Estimate(customer="Jane Doe", address="1 Main St, Denver, CO 80211", title="DOE_1_REC", sections=[
        Section(name="Kitchen", room=Room(name="Kitchen"), items=[
            LineItem(description="1/2\" drywall - hung, taped", quantity=100, unit="SF", unit_price=2.72, group="Drywall"),
            LineItem(description="Install Kitchen Sink - single basin", quantity=1, unit_price=193.94,
                     group="Cabinets & Sink"),
        ]),
        Section(name="Pantry", room=Room(name="Pantry"), option="Pantry Repairs", items=[
            LineItem(description="Texture drywall - machine", quantity=50, unit="SF", unit_price=0.89),
        ]),
    ])


def test_scopes_group_by_trade_and_option():
    base, pantry = build_scopes(sample_estimate())
    assert [t.name for t in base.trades] == ["Drywall", "Plumbing / Shower"]
    assert base.trades[0].total == 326.40  # 272.00 + 20% O&P
    assert pantry.option == "Pantry Repairs" and pantry.total == 53.40


def test_customer_docs_render():
    est = sample_estimate()
    html = render(est, load_company(), "estimate")
    assert "Cost Summary" in html and "Optional: Pantry Repairs" in html and "Total Job Price with Optional" in html
    agreement = render(est, load_company(), "agreement")
    assert "Waivers and Acknowledgments" in agreement and "CUSTOMER SIGNATURE" in agreement
    assert "this agreement, it is not in the price" in agreement


def test_customer_scope_uses_ai_answer(monkeypatch):
    fake = {"intro": "How this estimate is organized. Pantry is optional.",
            "scopes": [{"option": "base", "areas": "Kitchen"}, {"option": "Pantry Repairs", "areas": "Pantry"}],
            "trades": [{"option": "", "trade": "Drywall", "items": [1], "bullets": ["Replace damaged drywall"], "note": ""},
                       {"option": "", "trade": "Plumbing", "items": [2], "bullets": ["Install kitchen sink"], "note": ""}]}
    monkeypatch.setattr(customer_mod.ai, "structured", lambda *a, **k: fake)
    est = customer_mod.write_customer_scope(sample_estimate())
    items = [i for _, i in est.all_items()]
    assert [i.trade for i in items] == ["Drywall", "Plumbing", "Drywall"]  # item 3 not assigned -> keyword guess
    base, pantry = build_scopes(est)
    assert base.trades[0].bullets == ["Replace damaged drywall"] and base.areas == "Kitchen"
    assert est.intro.startswith("How this estimate")


def test_room_height_recomputes_walls(tmp_path):
    from estimator.ingest.esx import load_esx_rooms
    (room,) = load_esx_rooms(make_esx(tmp_path / "job.esx"))
    openings = 3 * 80 / 12 + 3 * 4
    assert room.set_height(10).wall_sf == pytest.approx(44 * 10 - openings, abs=0.01)


def test_markup_applies_to_customer_documents_only():
    est = sample_estimate()
    plain = build_scopes(est)[0].total
    est.markup_pct = 5
    base = build_scopes(est)[0]
    assert base.total == pytest.approx(plain * 1.05, abs=0.02)
    assert base.total == round(sum(t.total for t in base.trades), 2)  # document always adds up
    assert est.grand_total == plain  # Xactimate-side totals unchanged


def test_markup_history_pairs_documents_with_xactimate(tmp_path):
    from estimator.markup import history, suggested
    lib = Library(tmp_path / "lib.db")
    est = sample_estimate()
    lib.add(est)
    customer_total = round(est.grand_total * 1.05, 2)
    lib.add_style_example(f"Reconstruction Estimate\nEstimate: DOE_1_REC\nTotal Job Price ${customer_total:,.2f}",
                          "customer_estimate", "doe.pdf")
    (row,) = history(lib)
    assert row.estimate == "DOE_1_REC" and suggested(lib) == 5.0
