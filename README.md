# Estimator

Drafts new reconstruction estimates from **your past Xactimate estimates**, your **job notes**, and the
**DocuSketch ESX** for the project. Then it writes them up as your **Reconstruction Estimate** and
**Reconstruction Agreement**, an Xactimate-style PDF, or Excel.

```
Xactimate PDFs ─────────► library: line items + the prices you've charged
Reconstruction Estimates/Agreements ─► style examples: how you word things for customers
                                │
notes + DocuSketch .ESX + photos ─► Claude scopes line items & quantities ─► prices from your history
                                                                         │
                                         Claude groups into trades + writes customer bullets
                                                                         │
            Reconstruction Estimate · Reconstruction Agreement · Xactimate-style PDF · Excel · CSV
```

## Setup (once)

```bash
pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...      # Windows (macOS/Linux: export ANTHROPIC_API_KEY=...)
```

PDFs of your templates are printed with Chrome or Edge, which most computers already have.

## 1. Load your history

Point it at your estimates folder. It searches all subfolders, skips files it has already imported,
and you can stop it and run it again at any time:

```bash
python -m estimator import "C:\Users\you\Documents\Estimates"
```

- **Xactimate PDFs** are read offline, so they cost nothing. Every room total is checked against the
  "Totals:" line in the PDF, and the log shows `all room totals match`.
- **Your Reconstruction Estimates / Agreements** are saved as style examples. Claude copies your
  wording from them.
- **Other PDFs** are read by Claude. Add `--no-ai` to skip them and spend nothing.

## 2a. New job: notes + DocuSketch

```bash
python -m estimator new --notes notes.txt --sketch "5517849v2.ESX" --photos photos/*.jpg ^
    --customer "Jane Doe" --address "123 Main St, Denver, CO 80211"
```

The `.ESX` from the DocuSketch folder is read directly: rooms, ceiling heights, wall SF (minus doors
and windows), floor SF, and floor perimeter (minus doorways), using the same math Xactimate uses. If your
notes say something is optional or priced separately (e.g. "pantry as optional add-on"), it goes into
its own optional section with its own total and billing row.

## 2b. Or convert an Xactimate estimate you already wrote

```bash
python -m estimator convert "Smith - Repair Estimate.pdf" --optional "Pantry=Pantry Repairs"
```

This reads the Xactimate PDF, groups the line items into your trades, writes the customer bullets, and
outputs your Reconstruction Estimate and Agreement.

## 3. Review and export: the web app

```bash
streamlit run app.py
```

The tabs are Library, New estimate, Convert Xactimate, Review & edit, Export, and Settings. In Review you
can edit line items, which trade each one falls under, optional add-ons, and the customer bullets.
Items marked `ai` weren't in your price history, so check those prices.

## Output formats

| Format | What it is |
|---|---|
| `estimate` | Your **Reconstruction Estimate**: trades with O&P-inclusive totals, bullets, exclusions, a 50/40/10 billing table, and a cost summary when there are optional add-ons |
| `agreement` | Your **Reconstruction Agreement**: the same scope, plus material selections, waivers, work-authorization terms, and a signature block |
| `xactimate` | A PDF laid out like an Xactimate estimate (it cannot be imported into Xactimate) |
| `excel`, `csv`, `json` | Line items. The JSON can be edited and re-exported with `python -m estimator export job.json --format agreement` |

## Changing the wording

- **Exclusions, waivers, agreement terms, billing %, license line**: `estimator/company_defaults.json`
- **Standard trade notes and trade order**: `estimator/trades.py`
- **How bullets are written**: `STYLE_GUIDE` in `estimator/customer.py`. Importing more of your customer
  documents also teaches it.
- **Layout**: `estimator/templates/*.html.j2`

## Notes

- Your estimates and customer data stay on your computer, in `data/` (ignored by git). Only the text
  needed for each request is sent to Claude.
- Tests: `python -m pytest`. Model: `claude-opus-5-5`; set `ESTIMATOR_MODEL` to change it.
