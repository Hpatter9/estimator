"""The Claude skill's scripts: generated readers stay in sync, and the standalone scripts work."""
import json
import subprocess
import sys
import zipfile

from PIL import Image

from estimator import skill_build
from tests.test_formats import make_esx, make_xactimate_pdf

SCRIPTS = skill_build.SKILL / "scripts"


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                          cwd=cwd, check=True).stdout


def test_generated_readers_are_up_to_date():
    """If this fails: run `py -m estimator build-skill` (or skill_build.regenerate_scripts()) and commit."""
    assert (SCRIPTS / "read_xactimate.py").read_text(encoding="utf-8") == skill_build.generated_read_xactimate()
    assert (SCRIPTS / "read_esx.py").read_text(encoding="utf-8") == skill_build.generated_read_esx()


def test_read_esx_script_matches_package(tmp_path):
    from estimator.ingest.esx import read_esx
    esx = make_esx(tmp_path / "job.esx")
    out = run("read_esx.py", esx, "--json", tmp_path / "rooms.json", "--height", "Kitchen=10")
    (room,) = json.loads((tmp_path / "rooms.json").read_text())
    (pkg,) = read_esx(esx)
    assert room["floor_sf"] == pkg.floor_sf and room["floor_perimeter_lf"] == pkg.floor_perimeter_lf
    assert room["height_ft"] == 10 and room["wall_sf"] == round(pkg.ceiling_perimeter_lf * 10 - pkg.openings_sf, 2)
    assert "Kitchen" in out


def test_read_xactimate_script(tmp_path):
    pdf = make_xactimate_pdf(tmp_path / "x.pdf")
    out = run("read_xactimate.py", pdf, "--json", tmp_path / "x.json")
    data = json.loads((tmp_path / "x.json").read_text())
    assert "all room totals match" in out and data["estimate_number"] == "DOE_1_REC"
    assert [i["unit_price"] for i in data["sections"][0]["items"]] == [2.72, 68.02]


def sample_job() -> dict:
    return {"customer": "Jane Doe", "address": "1 Main St, Denver, CO 80211", "estimate_number": "DOE_1_REC",
            "markup_pct": 5, "intro": "How this estimate is organized.",
            "sections": [
                {"name": "Kitchen", "option": "", "items": [
                    {"description": "1/2\" drywall - hung, taped", "quantity": 100, "unit": "SF", "unit_price": 2.72,
                     "trade": "Drywall"},
                    {"description": "Mystery item", "quantity": 1, "unit": "EA", "unit_price": 50, "trade": "Plumbing",
                     "price_source": "estimated"}]},
                {"name": "Pantry", "option": "Pantry Repairs", "items": [
                    {"description": "Texture drywall - machine", "quantity": 50, "unit": "SF", "unit_price": 0.89,
                     "trade": "Drywall"}]}],
            "trades": [{"trade": "Drywall", "option": "", "bullets": ["Replace damaged drywall"], "note": ""}],
            "selections": [{"title": "Vinyl Plank — Bath", "fields": [["Brand", "DuraLux"]]}]}


def test_render_all_documents(tmp_path):
    (tmp_path / "estimate.json").write_text(json.dumps(sample_job()))
    out = run("render.py", tmp_path / "estimate.json", "--out", tmp_path / "out")
    pdfs = sorted(p.name for p in (tmp_path / "out").glob("*.pdf"))
    assert pdfs == ["Jane Doe - Reconstruction Agreement.pdf", "Jane Doe - Reconstruction Estimate.pdf",
                    "Jane Doe - Xactimate style.pdf"]
    # 272.00 + 20% O&P = 326.40; +5% markup = 342.72.  50 + O&P = 60; +5% = 63.00
    assert "$342.72" in out and "$405.72" in out and "1 items priced without price-book history" in out
    import pdfplumber
    with pdfplumber.open(tmp_path / "out" / "Jane Doe - Reconstruction Estimate.pdf") as pdf:
        text = "\n".join(p.extract_text() for p in pdf.pages)
    assert "Cost Summary" in text and "Optional: Pantry Repairs" in text and "DOE_1_REC" in text


def test_price_lookup(tmp_path):
    out = run("price_lookup.py", "drywall")
    assert "drywall" in out.lower()


def test_photo_sheets(tmp_path):
    with zipfile.ZipFile(tmp_path / "photos.zip", "w") as z:
        for n in range(14):
            img = tmp_path / f"p{n}.jpg"
            Image.new("RGB", (800, 600), (n * 15, 80, 120)).save(img)
            z.write(img, f"job/p{n}.jpg")
    out = run("photo_sheets.py", tmp_path / "photos.zip", "--out", tmp_path / "sheets")
    assert "14 photos -> 2 contact sheets" in out
    assert (tmp_path / "sheets" / "sheet_02.jpg").exists() and (tmp_path / "sheets" / "photo_014.jpg").exists()


def test_package_contains_skill_files(tmp_path):
    out = skill_build.package(tmp_path / "s.skill")
    names = zipfile.ZipFile(out).namelist()
    assert "forefront-estimate/SKILL.md" in names and "forefront-estimate/scripts/render.py" in names
    assert not any(n.endswith(".txt") or "__pycache__" in n for n in names)


def test_build_leaves_tracked_files_alone(tmp_path):
    from estimator.config import Company
    from estimator.library import Library
    before = {p: p.read_bytes() for p in skill_build.SKILL.rglob("*") if p.is_file()}
    lib = Library(tmp_path / "lib.db")
    from estimator.ingest import import_into_library
    from tests.test_formats import make_xactimate_pdf as mk
    mk(tmp_path / "a.pdf")
    import_into_library(lib, [tmp_path / "a.pdf"], use_ai=False, progress=lambda m: None)
    info = skill_build.build(lib, Company(markup_pct=4), tmp_path / "dist" / "forefront-estimate.skill")
    assert {p: p.read_bytes() for p in skill_build.SKILL.rglob("*") if p.is_file()} == before
    z = zipfile.ZipFile(info["file"])
    book = z.read("forefront-estimate/references/price_book.csv").decode()
    assert "R&R Angle stop valve" in book and info["markup"] == 4
    assert json.loads(z.read("forefront-estimate/assets/company.json"))["markup_pct"] == 4
