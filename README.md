# Estimator

Drafts new restoration/construction estimates from **your past estimates**, your **job notes**, and the
**DocuSketch** measurements for the project. Then it exports the result in whatever format you need.

```
past estimates ──► library (line items + your historical prices)
                         │
notes + DocuSketch + photos ──► Claude drafts scope & quantities ──► prices filled from your history
                                                                    │
                     Xactimate-style PDF · your company template · Excel · CSV · JSON
```

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # from console.anthropic.com
```

## Use it in the browser

```bash
streamlit run app.py
```

1. **Past estimates**: upload your old estimates (Xactimate PDFs, your own PDFs, CSV/XLSX). Do this once. The more you add, the better it gets.
2. **New estimate**: type your notes and upload the DocuSketch export (PDF measurement report, CSV/XLSX, or ESX), plus photos if you want.
3. **Review & edit**: change any line item, quantity or price. Rows marked `ai` weren't in your price history, so check those.
4. **Export**: download as an Xactimate-style PDF, your company template (HTML + PDF), Excel, or CSV.

Put your company name, address, logo and terms under **Settings** (saved to `data/company.json`).

## Or from the command line

```bash
python -m estimator import past/*.pdf past/*.xlsx
python -m estimator prices --search drywall
python -m estimator new --notes examples/notes_sample.txt \
    --sketch examples/docusketch_rooms_sample.csv --photos photos/*.jpg \
    --customer "Jane Doe" --address "123 Main St" \
    --format xactimate --format company --format excel
python -m estimator export output/<estimate>.json --format excel   # re-export after editing the JSON
```

## How it decides things

- **Scope and quantities**: Claude reads your notes, photos and room measurements, looks at your 3 most similar past jobs, and writes line items the way you have scoped similar jobs. Quantities come from the measurements (walls → wall SF, flooring → floor SF, baseboard → perimeter LF, flood cuts → perimeter × cut height).
- **Prices**: when a line item matches one in your history, it uses the **median price you've charged**. Only items you've never used get a Claude-suggested price, and those are flagged.
- **Questions**: when something important is unclear (e.g. "Is the pad wet?"), it scopes the likely option and lists the question for you.

## Customizing the output

- **Your template**: edit `estimator/templates/company_estimate.html.j2` (plain HTML + CSS). PDF is printed with Chrome/Chromium if installed; otherwise you get the HTML and can print it to PDF.
- **Xactimate-style PDF**: `estimator/export/xactimate_style.py`. This produces a PDF with the same layout as an Xactimate estimate. It is not a file Xactimate can import. To load an estimate into Xactimate, use the Excel export as your checklist.
- **New format**: add a writer in `estimator/export/` and register it in `FORMATS` in `estimator/export/__init__.py`.

## Files

| Path | What it does |
|---|---|
| `estimator/ingest/estimate_pdf.py` | Reads past estimate PDFs (Claude, or an offline Xactimate parser with `--no-ai`) |
| `estimator/ingest/spreadsheet.py` | CSV/XLSX estimates and room tables (flexible column names) |
| `estimator/ingest/docusketch.py` | DocuSketch room measurements |
| `estimator/library.py` | SQLite library, similar-job search, price book |
| `estimator/generate.py` | Drafts the new estimate |
| `estimator/export/` | Output formats |
| `app.py` | Web app |

Run the tests with `python -m pytest`.

The model defaults to `claude-opus-5-5`. To use a different one, set `ESTIMATOR_MODEL`.
