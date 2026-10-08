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

## Setup on Windows (once)

You need [Python](https://www.python.org/downloads/) (tick **"Add python.exe to PATH"** when installing)
and [Git](https://git-scm.com/download/win). Then, in PowerShell:

```powershell
cd $HOME\Documents
git clone https://github.com/hpatter9/estimator.git
cd estimator
git checkout claude/modest-wozniak-p8l4u6
py -m pip install -r requirements.txt
```

For the AI features, add your key from console.anthropic.com (one time, then open a new PowerShell window):

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

PDFs of your templates are printed with Edge or Chrome, which Windows already has.

## 1. Load your history

Point it at your estimates folder. It searches all subfolders, skips files it has already imported,
and you can stop it and run it again at any time:

```bash
py -m estimator import "C:\Users\you\Documents\Estimates" --no-ai
py -m estimator list
py -m estimator markup
```

- **Xactimate PDFs** are read offline, so they cost nothing. Every room total is checked against the
  "Totals:" line in the PDF, and the log shows `all room totals match`.
- **Your Reconstruction Estimates / Agreements** are saved as style examples. Claude copies your
  wording from them.
- **Other PDFs** are read by Claude. With `--no-ai` they are skipped and nothing is spent; you can run the
  import again later without `--no-ai` to pick them up.

`markup` pairs each customer document with the Xactimate it names and shows how much you marked up
each job. New customer documents use the median of those jobs, unless you set `markup_pct` in
`data/company.json` or pass `--markup 5`.

## 2a. New job: notes + DocuSketch

```bash
py -m estimator new --notes notes.txt --sketch "5517849v2.ESX" --height "Kitchen=10" `
    --customer "Jane Doe" --address "123 Main St, Denver, CO 80211"
```

The `.ESX` from the DocuSketch folder is read directly: rooms, wall SF (minus doors and windows),
floor SF, and floor perimeter (minus doorways), using the same math Xactimate uses. Checked against a
finished Xactimate: floor SF and perimeter match exactly, and wall SF is within 1%. DocuSketch exports
every room with an 8' ceiling, so give real heights with `--height "Kitchen=10"` (repeatable) or
`--default-height 8.75`, or set them in the room table in the web app. If your
notes say something is optional or priced separately (e.g. "pantry as optional add-on"), it goes into
its own optional section with its own total and billing row.

## 2b. Or convert an Xactimate estimate you already wrote

```bash
py -m estimator convert "Smith - Repair Estimate.pdf" --optional "Pantry=Pantry Repairs"
```

This reads the Xactimate PDF, groups the line items into your trades, writes the customer bullets, and
outputs your Reconstruction Estimate and Agreement.

## 3. Review and export: the web app

```bash
py -m streamlit run app.py
```

The tabs are Library, New estimate, Convert Xactimate, Review & edit, Export, and Settings. In Review you
can edit line items, which trade each one falls under, optional add-ons, the customer bullets, and
material selections (optional; only the Agreement shows them). The Export tab has the markup.
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
