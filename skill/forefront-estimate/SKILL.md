---
name: forefront-estimate
description: Forefront Building + Restoration's estimating workflow. Drafts reconstruction estimates from a DocuSketch .ESX sketch, job notes and site photos, priced from Forefront's own price book, and produces their Reconstruction Estimate, Reconstruction Agreement and Xactimate-format PDFs. Also turns an existing Xactimate estimate PDF into the customer Reconstruction Estimate / Agreement. Use this whenever someone wants to write, price, scope, convert, revise or re-send a reconstruction / repair / water / fire / mold estimate or agreement, uploads an .ESX or DocuSketch export, an Xactimate PDF, or a zip of job photos, or mentions Forefront estimates, even if they don't say "skill".
---

# Forefront estimate

Turn a job into Forefront's documents:

- **Reconstruction Estimate**: the customer summary, with trades, O&P-inclusive totals, plain-English bullets, exclusions and a 50/40/10 billing table.
- **Reconstruction Agreement**: the same scope, plus material selections, waivers, work-authorization terms and a signature block.
- **Xactimate Estimate**: always laid out like Forefront's real Xactimate exports (see "The Xactimate PDF" below), for the estimator, adjusters and customers who want line items.

Everything runs with the scripts in `scripts/` (Python + reportlab, already in the sandbox). Work in a scratch
folder and save finished files to the outputs folder (`/mnt/user-data/outputs` on claude.ai).

## Pick the path

- **New job**: an ESX and/or notes and/or photos. Do steps 1–5.
- **Convert an Xactimate PDF**: someone uploads an Xactimate estimate and wants the customer documents. Run
  `python scripts/read_xactimate.py estimate.pdf --json est.json` and confirm the summary says
  "all room totals match". Keep its items and prices as they are (`price_source: "xactimate"`), then do steps 3–5,
  rendering with `--only estimate,agreement` unless the Xactimate PDF is asked for. Use the Xactimate's
  estimate name as `estimate_number`. While you have the line items in front of you, look for the slips an
  estimator would want caught before the customer sees a price: an install with no matching removal (new carpet
  but no carpet removal), a quantity far off the room size (1 SF of membrane on a 250 SF floor), a labor minimum
  triggered by such a slip, or $0 open/bid items. Don't change the Xactimate; mention them in the report.
- **Revise**: change the existing estimate.json and re-run step 4. Don't start over.

## 1. Read the inputs

- **DocuSketch .ESX**: `python scripts/read_esx.py job.ESX --json rooms.json`. It prints floor SF, wall SF
  (minus doors and windows), floor and ceiling perimeter per room. DocuSketch exports every room at an 8' ceiling.
  If the user gave real heights, pass `--height "Kitchen=10"` (repeatable) or `--default-height 9`. If not, carry
  on at 8' and list it as an assumption, because walls change with height and floors don't.
- **Encrypted ESX**: newer DocuSketch exports wrap the sketch in an encrypted `XACTDOC.ZIPXML`, and read_esx.py
  says "no sketch found inside the ESX". Then take the measurements from the floor-plan images in the same
  sketches zip (`measurements_<floor>.png` for room sizes, `image_wall_measurements_<floor>.png` for wall
  lengths): rooms are length x width, floor perimeter is 2 x (L + W), walls are perimeter x height minus doors
  and windows. Check the images are actually this property (room names and layout match the photos) before using
  them; a mismatched image has come through before. Watch for rooms whose labelled rectangles overlap (an
  L-shaped living/dining) and don't count the overlap twice.
- **Photos**: for a zip or several images, run `python scripts/photo_sheets.py photos.zip --out photos/` and view
  the contact sheets. Open single `photo_###.jpg` files only where you need detail. Note what the photos show
  that matters for scope: materials, damage extent, texture, trim profile, cabinets, flooring type.
- **CompanyCam**: a shared gallery link (`app.companycam.com/galleries/...`) opens without a login; a project link
  (`/projects/...`) needs the user signed in. Open it in the browser and look through every photo. CompanyCam
  projects usually include **before-loss photos** (furnished rooms); those settle the original finishes: flooring
  type and color, closet door style, wall texture, ceiling texture, mirrors, tub surround. Prefer what they show
  over guesses from post-demo photos.
- **Notes**: the estimator's notes say which rooms are affected and what's being done. They win over
  assumptions.
- A DocuSketch share link (`app.docusketch.com/player/...`) is a 360° viewer. Its photos usually can't be
  read from the link, so ask for the downloaded photos or photo report instead.
- **Xactimate price list (.PLX)**: encrypted by Xactware and can't be read. Prices come from
  `references/xactimate_prices.csv` instead, which is imported each month from a rate-sheet PDF exported from
  Xactimate (`py -m estimator import-pricelist`). Set `price_list` in estimate.json to the list those prices came
  from (the `list` column header in price_lookup output, e.g. `CODE8X_OCT26`), and say so in the report when the
  job is in another market (a Boulder job priced on the Denver list).

## 2. Scope the line items

Read `references/scoping_guide.md` (quantity rules, items Forefront usually includes) and skim
`references/common_items.md` (most-used items and typical prices). For each item:
`python scripts/price_lookup.py <words> [--unit SF]`, then copy its description and unit exactly. Price it at the
`list` column (this month's Xactimate price list, `price_source: "price_list"`) whenever the item has one, and at
`median` from Forefront's history (`price_source: "price_book"`) only when it doesn't. When two wordings exist for
the same work, pick the one on the list. Items with neither get a realistic price and
`price_source: "estimated"`. The user needs to check those, so they are flagged in the PDF and the summary.
`python scripts/price_lookup.py --components <words>` shows material / equipment / labor component costs, for
pricing a bid item or explaining a price.

Only scope the affected rooms; sketches often cover the whole house. Group items into sections by room, plus
"General Conditions". When the notes call something optional or priced separately, give those sections an
`option` name. When something important is unclear, scope the likely answer and add a question.

Follow the General Conditions rules in the scoping guide: no supervision on small jobs, electrical as device
line items in each room (never electrician hours), and masking in the room it protects, not General Conditions.

Item notes print on the Xactimate PDF under the line, the way Forefront's Xactimate notes do, so write them for
an adjuster (reason or measurement), not as reminders to yourself.

## 3. Write the customer wording

Read `references/house_style.md`. Give every line item a `trade`, then write one `trades` entry per trade
(per option) with bullets in Forefront's wording and the standard note where one applies. Add `scopes` areas
and an `intro` only when there are optional add-ons. Agreements only: add `selections` when the user gives
product details (brand, product, SKU/color, size, photo).

## 4. Build the documents

Write `estimate.json` in the format in `references/estimate_format.md`, including the Xactimate fields:
`level` (e.g. "1st Floor"), `type_of_estimate` (Water / Fire / Mold), `price_list`, `sketches` (the DocuSketch
floor-plan image per floor, preferably `image_wall_measurements_<floor>.png`), and `rooms` whose names match the
section names exactly. Then:

```
python scripts/render.py estimate.json --out /mnt/user-data/outputs
```

Use `--only estimate,agreement` or `--only xactimate` when only some are wanted. The script prints the totals by
trade; check that they look sane (no trade at $0, no missing trades, warnings about items without a trade).

Markup applies to the Estimate and Agreement only, using `markup_pct` from `assets/company.json` unless the
user gives one or estimate.json sets it. Say which markup you used.

### The Xactimate PDF

`scripts/xactimate_pdf.py` always produces Forefront's Xactimate export layout; don't build a different one:

- Letterhead on every page: logo (`assets/xact_logo.png`), **Forefront Building & Restoration**, Corporate Office,
  address, phone, IICRC number. Footer: estimate name, date, "Page: N".
- Cover (pages 1–2): Client, Property, Operator, Estimator / Position / Company with Business phone and E-mail,
  Type of Estimate, Date Entered, Price List, Labor Efficiency, Estimate; **Total Estimate**; the 50% deposit line;
  and Forefront's policy wording (Xactimate, Please consider the following 1–6). All of it comes from
  `company.json` -> `"xactimate"`; never reword it per job.
- Line items: estimate name and "Source - DocuSketchConverter" centered; General Conditions; then each level
  heading ("1st Floor") with its rooms. Each room has its dimension block, then a DESCRIPTION / QTY / REMOVE /
  REPLACE / TAX / O&P / TOTAL table with items numbered straight through the estimate and **grouped under italic
  sub-headings** (Drywall, Insulation, Electrical, Plumbing, Tub and Surround, Paint, Baseboard, Snaplock
  Laminate, Carpet, Tile, Doors and Casing, Window Trim, Cleaning ...), then "Totals: <room>". Groups come from the
  description automatically; set an item's `group` only when it lands somewhere wrong.
- Then Total for the level, Line Item Totals, Grand Total Areas, Recap by Room, Recap by Category (Xactimate
  category names, overhead and profit, total) with the IICRC closing line, and the landscape sketch pages. No
  Summary for Dwelling or Recap of Taxes pages.

After rendering, look at a few pages (`pdftoppm -r 60 -png`) to confirm nothing landed in the wrong group.

### File names

Save the documents as `<Customer Last Name> - Reconstruction Estimate.pdf`,
`<Customer Last Name> - Reconstruction Agreement.pdf` and `<Customer Last Name> - Xactimate Estimate.pdf`
(render.py names them after the full customer name; rename to the last name).

## 5. Report back

Keep it short; the estimator reads this between jobs. Cover:
1. The documents created.
2. The total, plus optional add-ons.
3. Items priced without price-book history.
4. Assumptions, especially 8' ceilings and rooms left out.
5. Your questions: the few (about 3) whose answers would change the price most. Fold the minor ones into the
   assumptions instead of asking.

Also keep `estimate.json` in the outputs, so changes later are quick.

## Company details

`assets/company.json` holds Forefront's name, address, billing schedule, exclusions, waivers, agreement
terms, default markup, and the `"xactimate"` block (letterhead, estimator details, cover wording, IICRC line);
`assets/logo.png` is the customer-document logo and `assets/xact_logo.png` the Xactimate letterhead logo.
`references/price_book.csv` is generated from Forefront's past Xactimate estimates (no customer data) by
`py -m estimator build-skill` on the estimating PC. `references/xactimate_prices.csv` (every line item on the
current Xactimate price list, REMOVE and REPLACE split) and `references/component_costs.csv` come from
`py -m estimator import-pricelist <items.pdf> --components <components.pdf>`. Re-uploading the rebuilt skill
refreshes prices.
