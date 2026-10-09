---
name: forefront-estimate
description: Forefront Building + Restoration's estimating workflow. Drafts reconstruction estimates from a DocuSketch .ESX sketch, job notes and site photos, priced from Forefront's own price book, and produces their Reconstruction Estimate, Reconstruction Agreement and Xactimate-style PDFs. Also turns an existing Xactimate estimate PDF into the customer Reconstruction Estimate / Agreement. Use this whenever someone wants to write, price, scope, convert, revise or re-send a reconstruction / repair / water / fire / mold estimate or agreement, uploads an .ESX or DocuSketch export, an Xactimate PDF, or a zip of job photos, or mentions Forefront estimates, even if they don't say "skill".
---

# Forefront estimate

Turn a job into Forefront's documents:

- **Reconstruction Estimate**: the customer summary, with trades, O&P-inclusive totals, plain-English bullets, exclusions and a 50/40/10 billing table.
- **Reconstruction Agreement**: the same scope, plus material selections, waivers, work-authorization terms and a signature block.
- **Xactimate-style PDF**: line items room by room at price-book prices, for the estimator and adjusters.

Everything runs with the scripts in `scripts/` (Python + reportlab, already in the sandbox). Work in a scratch
folder and save finished files to the outputs folder (`/mnt/user-data/outputs` on claude.ai).

## Pick the path

- **New job**: an ESX and/or notes and/or photos. Do steps 1–5.
- **Convert an Xactimate PDF**: someone uploads an Xactimate estimate and wants the customer documents. Run
  `python scripts/read_xactimate.py estimate.pdf --json est.json` and confirm the summary says
  "all room totals match". Keep its items and prices as they are (`price_source: "xactimate"`), then do steps 3–5.
  Use the Xactimate's estimate name as `estimate_number`.
- **Revise**: change the existing estimate.json and re-run step 4. Don't start over.

## 1. Read the inputs

- **DocuSketch .ESX**: `python scripts/read_esx.py job.ESX --json rooms.json`. It prints floor SF, wall SF
  (minus doors and windows), floor and ceiling perimeter per room. DocuSketch exports every room at an 8' ceiling.
  If the user gave real heights, pass `--height "Kitchen=10"` (repeatable) or `--default-height 9`. If not, carry
  on at 8' and list it as an assumption, because walls change with height and floors don't.
- **Photos**: for a zip or several images, run `python scripts/photo_sheets.py photos.zip --out photos/` and view
  the contact sheets. Open single `photo_###.jpg` files only where you need detail. Note what the photos show
  that matters for scope: materials, damage extent, texture, trim profile, cabinets, flooring type.
- **Notes**: the estimator's notes say which rooms are affected and what's being done. They win over
  assumptions.
- A DocuSketch share link (`app.docusketch.com/player/...`) is a 360° viewer. Its photos usually can't be
  read from the link, so ask for the downloaded photos or photo report instead.

## 2. Scope the line items

Read `references/scoping_guide.md` (quantity rules, items Forefront usually includes) and skim
`references/common_items.md` (most-used items and typical prices). For each item:
`python scripts/price_lookup.py <words> [--unit SF]`, then copy its description and unit, and use
`median_price`. Items with no match get a realistic price and `price_source: "estimated"`. The user needs to
check those, so they are flagged in the PDF and the summary.

Only scope the affected rooms; sketches often cover the whole house. Group items into sections by room, plus
"General Conditions". When the notes call something optional or priced separately, give those sections an
`option` name. When something important is unclear, scope the likely answer and add a question.

## 3. Write the customer wording

Read `references/house_style.md`. Give every line item a `trade`, then write one `trades` entry per trade
(per option) with bullets in Forefront's wording and the standard note where one applies. Add `scopes` areas
and an `intro` only when there are optional add-ons. Agreements only: add `selections` when the user gives
product details (brand, product, SKU/color, size, photo).

## 4. Build the documents

Write `estimate.json` in the format in `references/estimate_format.md`, then:

```
python scripts/render.py estimate.json --out /mnt/user-data/outputs
```

Use `--only estimate,agreement` or `--only xactimate` when only some are wanted. The script prints the totals by
trade; check that they look sane (no trade at $0, no missing trades, warnings about items without a trade).

Markup applies to the Estimate and Agreement only, using `markup_pct` from `assets/company.json` unless the
user gives one or estimate.json sets it. Say which markup you used.

## 5. Report back

Keep it short. Cover:
1. The documents created.
2. The total, plus optional add-ons.
3. Items priced without price-book history.
4. Assumptions, especially 8' ceilings and rooms left out.
5. Your questions.

Also keep `estimate.json` in the outputs, so changes later are quick.

## Company details

`assets/company.json` holds Forefront's name, address, billing schedule, exclusions, waivers, agreement
terms and default markup; `assets/logo.png` is the logo. `references/price_book.csv` is generated from
Forefront's past Xactimate estimates (no customer data) by `py -m estimator build-skill` on the estimating PC.
Re-uploading the rebuilt skill refreshes prices.
