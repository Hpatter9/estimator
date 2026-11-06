---
name: "forefront-estimate"
description: "Forefront Building + Restoration's estimating workflow. Drafts reconstruction estimates from a DocuSketch .ESX sketch, job notes and site photos, priced from Forefront's own price book, and produces their Reconstruction Estimate, Reconstruction Agreement and Xactimate-format PDFs, then drafts the send-off email in Gmail. Also turns an existing Xactimate estimate PDF into the customer Reconstruction Estimate / Agreement. Use this whenever someone wants to write, price, scope, convert, revise, re-send or email a reconstruction / repair / water / fire / mold estimate or agreement, uploads an .ESX or DocuSketch export, an Xactimate PDF, or a zip of job photos, or mentions Forefront estimates, even if they don't say \"skill\"."
---

# Forefront estimate

Turn a job into Forefront's documents:

- **Reconstruction Estimate**: the customer summary, with trades, O&P-inclusive totals, plain-English bullets, exclusions and a 50/40/10 billing table.
- **Reconstruction Agreement**: the same scope, plus material selections, waivers, work-authorization terms and a signature block.
- **Xactimate Estimate**: always laid out like Forefront's real Xactimate exports (see "The Xactimate PDF" below), for the estimator, adjusters and customers who want line items.
- **Photo report**: key photos with a one-line caption each, on the Xactimate letterhead, for the adjuster (step 6).
- **Send-off email**: a Gmail draft in Hunter's voice, with the right PDF attached and the job's log address bcc'd (step 6).

Everything runs with the scripts in `scripts/` (Python + reportlab, already in the sandbox). Work in a scratch
folder and save finished files to the outputs folder (`/mnt/user-data/outputs` on claude.ai; in the Forefront
hub, the job folder's `estimate/` directory).

## Pick the path

- **New job**: an ESX and/or notes and/or photos. Do steps 1–6.
- **Convert an Xactimate PDF**: someone uploads an Xactimate estimate and wants the customer documents. Run
  `python scripts/read_xactimate.py estimate.pdf --json est.json` and confirm the summary says
  "all room totals match". Keep its items and prices as they are (`price_source: "xactimate"`), then do steps 3–6,
  rendering all three documents as usual (the Xactimate PDF is rebuilt in Forefront's layout from its items). Use the Xactimate's
  estimate name as `estimate_number`. While you have the line items in front of you, look for the slips an
  estimator would want caught before the customer sees a price: an install with no matching removal (new carpet
  but no carpet removal), a quantity far off the room size (1 SF of membrane on a 250 SF floor), a labor minimum
  triggered by such a slip, or $0 open/bid items. Don't change the Xactimate; mention them in the report.
- **Revise**: change the existing estimate.json and re-run step 4. Don't start over. If the user only needs one
  document right now ("I only need the estimate for now"), use `--only estimate`; otherwise render all three.

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
  (`/projects/...`) needs the user signed in. The gallery is built by JavaScript, so a plain WebFetch only returns
  the page shell: open it in the browser (built-in browser or Chrome), click a thumbnail to get the lightbox,
  and step through every photo. Always do this when a link is given; don't report that it couldn't be opened
  without trying the browser. CompanyCam projects usually include **before-loss photos** (furnished rooms);
  those settle the original finishes: flooring type and color, closet door style, wall texture, ceiling texture,
  mirrors, tub surround. Prefer what they show over guesses from post-demo photos.
- **Notes**: the estimator's notes say which rooms are affected and what's being done. They win over
  assumptions.
- A DocuSketch share link (`app.docusketch.com/player/...`) is a 360° viewer. Its photos usually can't be
  read from the link, so ask for the downloaded photos or photo report instead.
- **Xactimate price list (.PLX)**: encrypted by Xactware and can't be read. Prices come from
  `references/xactimate_prices.csv` instead, which is imported each month from a rate-sheet PDF exported from
  Xactimate (`py -m estimator import-pricelist`). Pick the list for the job's market (Boulder County address ->
  COBO8X, Denver metro -> CODE8X) and set `price_list` to it. If the job's market isn't loaded (e.g. Colorado
  Springs), use the nearest one and say so in the report.

## 2. Scope the line items

Read `references/scoping_guide.md` (quantity rules, items Forefront usually includes) and skim
`references/common_items.md` (most-used items and typical prices). For each item:
`python scripts/price_lookup.py <words> [--unit SF] [--list COBO8X_OCT26]`, then copy its description and unit
exactly. It shows one price column per Xactimate price list loaded (CODE8X = Denver metro, COBO8X = Boulder County).
Price from the list for the job's market whenever the item is on it (`price_source: "price_list"`), and set
`price_list` in estimate.json to that list; use `median` from Forefront's history (`price_source: "price_book"`)
only when the item isn't on the list. When two wordings exist for
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

### Forefront scoping rules (these override the general guide)

- **Paint only the affected walls, per typical insurance rules — not every wall in the room.** A wall is
  affected when drywall on it was removed or patched, or when the ceiling drywall was pulled all the way to
  that wall (the corner tape and texture make the wall a repair too). A bathroom with half its ceiling pulled
  and one wall strip removed gets its ceiling and the two walls those repairs tie into, not four walls. Once a
  wall or ceiling is affected, paint that whole continuous surface (into adjoining rooms if it continues with
  no break), never just a patch. State in the line-item note which walls are counted and why.
- **Flooring**: when flooring is replaced, replace all continuous flooring of that material on that level in
  the base scope, not as an option. Don't scope flooring at all when the photos/notes show it wasn't affected.
- **Doors**: bypass (sliding) and interior doors are not detached for drywall or paint work; detach & reset
  them only when flooring is being replaced under them.
- **Keep paint prep simple.** Don't list hardware detach & reset for painting (towel bars, mirrors, outlet and
  switch covers, thermostats, registers, recessed-light trims, fan covers, vanity lights). Masking covers
  that. Do keep electrical items that the drywall work itself requires, such as a recessed light in a removed
  ceiling section.
- **Texture**: price the texture that matches the existing surface (skim coat for smooth, machine/orange peel,
  knockdown), but the customer wording and line notes say "texture to match existing" — don't promise
  "smooth" or a specific finish.
- Basic masking goes in the room it protects, never in General Conditions.

## 3. Write the customer wording

Read `references/house_style.md`. Give every line item a `trade`, then write one `trades` entry per trade
(per option) with bullets in Forefront's wording and the standard note where one applies. Add `scopes` areas
and an `intro` only when there are optional add-ons. Agreements only: add `selections` when the user gives
product details (brand, product, SKU/color, size, photo). When the owner still has to pick finishes (flooring,
tile, doors, cabinets), add a `selections` entry per finish as an allowance: the material cost per unit from
`price_lookup.py --components <words> --list <market>` (hand-entered costs such as snaplock laminate live in
`references/component_costs_manual.csv`), the quantity with waste, the allowance total, the pre-loss finish,
"Brand / product / color: To be selected by Owner", what happens over allowance, and `"viewed": "To be selected"`.

Signature blocks: the Reconstruction Agreement and any Material Selection Approval sheet carry only the
Customer / Homeowner signature block — no Forefront representative signature line.

## 4. Build the documents

Write `estimate.json` in the format in `references/estimate_format.md`, including the Xactimate fields:
`level` (e.g. "1st Floor"), `type_of_estimate` (Water / Fire / Mold), `price_list`, `sketches` (the DocuSketch
floor-plan image per floor, preferably `image_wall_measurements_<floor>.png`), and `rooms` whose names match the
section names exactly. Then:

```
python scripts/render.py estimate.json --out /mnt/user-data/outputs
```

Always produce all three documents - Reconstruction Estimate, Reconstruction Agreement and Xactimate Estimate - on
every job and every revision, and deliver all three. Use `--only` only when the user explicitly asks for just one
or two. Before reporting back, confirm the script printed three `->` lines. The script prints the totals by
trade; check that they look sane (no trade at $0, no missing trades, warnings about items without a trade).

**Selections sign-off**: when the owner needs to approve finishes before ordering (or asks for a selection sheet), fill `selections` in estimate.json as in step 3 and run `python scripts/render.py estimate.json --out <dir> --only selections`. It writes `<Last Name> - Material Selection Approval.pdf`: each selection with an owner-initials line, the selection acknowledgments from company.json, and the customer signature block only. It is separate from the three documents and isn't sent unless asked.

Markup applies to the Estimate and Agreement only, using `markup_pct` from `assets/company.json` unless the
user gives one or estimate.json sets it ("bump it up by 15%" = `"markup_pct": 15`). Say which markup you used.

### Customer-document layout rules

- **Never print the "All amounts include overhead and profit" note** (company.json `amounts_note`) on the
  Estimate or Agreement. If render.py still prints it, drop that line from the script before rendering.
- **A short estimate goes on one page.** The Job Total & Billing block may sit at the very bottom of page 1:
  use a 0.3" bottom margin with the footer at 0.12", H2 spaceBefore 6 on that heading, 3pt table padding and
  1pt spacers in the exclusions list. Rasterize (`pdftoppm -r 60 -png`) and confirm the page count.
- The logo in `assets/logo.png` is 800px wide and makes up most of the PDF's bytes; a 300–400px copy renders
  identically on screen and keeps the estimate PDF under ~15 KB, which matters for emailing (step 6).

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
  description automatically; set an item's `group` only when it lands somewhere wrong (e.g. "Thermostat - Detach
  & reset" needs `group: "Electrical"`).
- Then Total for the level, Line Item Totals, Grand Total Areas, Recap by Room, Recap by Category (Xactimate
  category names, overhead and profit, total) with the IICRC closing line, and the landscape sketch pages. No
  Summary for Dwelling or Recap of Taxes pages.

After rendering, look at a few pages (`pdftoppm -r 60 -png`) to confirm nothing landed in the wrong group.

### File names

render.py names the documents by the customer's last name: `<Last Name> - Reconstruction Estimate.pdf`,
`<Last Name> - Reconstruction Agreement.pdf` and `<Last Name> - Xactimate Estimate.pdf`.

## 5. Report back

Keep it short; the estimator reads this between jobs. Cover:
1. The documents created.
2. The total, plus optional add-ons.
3. Items priced without price-book history.
4. Assumptions, especially 8' ceilings and rooms left out.
5. Your questions: the few (about 3) whose answers would change the price most. Fold the minor ones into the
   assumptions instead of asking.

Also keep `estimate.json` in the outputs, so changes later are quick.

## 6. Send-off email (Gmail draft)

Every job gets a send-off email drafted in Hunter's Forefront Gmail (`hunter@forefrontteam.com`, the
`Gmail_cfe6ca4b` connector — never the personal account). Create it as a **draft**, never send. Use
`includeSignature: true` so his Gmail signature is appended; if the body has to change afterwards, delete the
draft and create a new one rather than `update_draft` (updating the body strips the signature).

**Addressing**
- To: the customer email from the job page (homeowner version) or the adjuster's email (adjuster version).
- Bcc: the job's log address, `office+<job#>@forefrontteam.com` — it's in the `mailto:` link on the job page
  (e.g. `?bcc=office%2B3226%40forefrontteam.com` → `office+3226@forefrontteam.com`). This files the email to
  the job in Homebase. Ask for the job number if the link wasn't pasted.
- Subject: `Your Reconstruction Estimate – <street address>` for homeowners; `<Insured last name> – <address> –
  Repair Estimate` with the claim number for adjusters.

**Voice** (match Hunter's real emails, which read like this): "Hi <first name>," / "Hey <first name>,",
short plain paragraphs, warm and unhurried, no bullet points, no corporate phrasing, closes with "Thanks
(again)," and the signature. Standard homeowner body:

> Hi <First>,
>
> Thank you for the opportunity to help with your home. Attached is the reconstruction estimate for <address>.
> It breaks the work down by trade so you can see exactly what's included, and the total comes to $<total>.
>
> <insurance paragraph — see variants>
>
> Take a look when you get a chance and let me know if you have any questions or want to talk through
> anything. If everything looks good, let me know and I'll move things forward on my end!
>
> Thanks again,

**Variants** (recipient × insurance):
- *Homeowner, insurance status unknown* (the default when nothing says): insurance paragraph = "Quick question -
  are you running this through insurance? If so, send me the claim number and your adjuster's contact info and
  I'll get my Xactimate estimate and photos over to them directly. That usually speeds things up. If you're
  paying out of pocket, just let me know and we can go from here."
- *Homeowner, insurance claim*: say the Xactimate version has gone / will go to the adjuster, that the adjuster's
  approval is the next step, and that the deductible is due at signing. Mention that supplements can change the
  number if the adjuster's scope differs.
- *Homeowner, out of pocket*: no insurance talk; mention the 50/40/10 billing schedule and that signing the
  Agreement gets them on the calendar; mention selections if the Agreement has allowances.
- *Adjuster*: professional and brief. Insured name, loss address, claim number, price list used, a 2–3 line
  summary of the scope logic (why the walls are included, texture to match, anything unusual) and a request to
  review/approve or call. Never mention markup. Attach the Xactimate Estimate **and a photo report** (key photos
  with a one-line description each); the Reconstruction Estimate is not for adjusters. Homeowner cc only if
  Hunter says so.

**Photo report** (adjuster send-offs): pick the 6–12 photos that justify the scope (damage, the extent of
removal, before-loss finishes that set the replacement), write one plain line per photo for an adjuster
("Ceiling drywall removed above the tub, approx. 4' x 6'"), put them in `picks.json` (format in the script's
docstring) and run:

```
python scripts/photo_report.py picks.json --photos photos/ --estimate estimate.json --out <outputs>
```

It writes `<Last Name> - Photo Report.pdf` on the Xactimate letterhead with client, property and claim number,
2 photos per page (`--per-page 4` for many photos). Add `"date_of_loss"` to picks.json when it's known.

**In the Forefront hub** (a `hub` / `mcp__hub__*` Gmail draft tool is available): pass the PDFs as file paths
in `attachments` and the hub attaches them directly and BCCs the Homebase log address itself. Skip the base64
steps below and the Chrome upload; they are only for claude.ai.

**Attachments**: homeowner gets the Reconstruction Estimate only (not the Agreement unless asked); adjuster gets
the Xactimate Estimate + photo report. The Gmail connector takes attachments as inline base64, which has to be
typed into the tool call, so:
1. Shrink first: render with a 300–400px logo, then `qpdf --recompress-flate --compression-level=9
   --object-streams=generate in.pdf small.pdf` (aim for under ~15 KB / 20k base64 chars).
2. `base64 -w0 small.pdf > est.b64`, then `fold -w 2000 est.b64 | split -l 1 -d - chunk_` and `cat` the chunks.
3. Re-type the whole string in a Bash heredoc, `tr -d '\n'`, and `cmp` it against `est.b64`; also `base64 -d`
   it and `cmp` against the PDF. Only when both match, pass the same string as `attachments[0].content`
   (`mimeType: application/pdf`, `filename: "<Last Name> - Reconstruction Estimate.pdf"`).
4. A decode error from the connector means a transcription slip — don't resend blind; re-verify.
Files too big for that path (Xactimate PDFs with sketches, photo reports): save them to the outputs folder and
attach through Claude in Chrome (`file_upload` into the Gmail compose's file input, which accepts files from the
session's outputs folder) when the extension is connected; otherwise create the draft without them and tell
Hunter exactly which file to drag on.

Report the draft in one line (recipient, bcc, subject, what's attached, what still needs attaching).

## Company details

`assets/company.json` holds Forefront's name, address, billing schedule, exclusions, waivers, agreement
terms, default markup, and the `"xactimate"` block (letterhead, estimator details, cover wording, IICRC line);
`assets/logo.png` is the customer-document logo and `assets/xact_logo.png` the Xactimate letterhead logo.
`references/price_book.csv` is generated from Forefront's past Xactimate estimates (no customer data) by
`py -m estimator build-skill` on the estimating PC. `references/xactimate_prices.csv` (every line item on the
current Xactimate price list, REMOVE and REPLACE split) and `references/component_costs.csv` come from
`py -m estimator import-pricelist <items.pdf> --components <components.pdf>`. Re-uploading the rebuilt skill
refreshes prices.