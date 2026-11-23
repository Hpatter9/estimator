---
name: "forefront-estimate"
description: "Forefront Building + Restoration's estimating workflow. Drafts reconstruction estimates from a DocuSketch sketch (pulled from app.docusketch.com in the browser or uploaded), CompanyCam photos (via the CompanyCam connector), job notes and site photos, priced from Forefront's own price book, and produces their Reconstruction Estimate, Reconstruction Agreement and Xactimate-format PDFs, then drafts the send-off email in Gmail, and once the price is agreed drafts the selections email (what the homeowner must pick and the budget per square foot) that comes before the Agreement. Also turns an existing Xactimate estimate PDF into the customer Reconstruction Estimate / Agreement. Use this whenever someone wants to write, price, scope, convert, revise, re-send or email a reconstruction / repair / water / fire / mold estimate or agreement, pastes a Homebase job page, uploads an .ESX or DocuSketch export, an Xactimate PDF, or a zip of job photos, asks what's next on an approved job or for a selections / allowance email, or mentions Forefront estimates, even if they don't say \"skill\"."
---

# Forefront estimate

Turn a job into Forefront's documents:

- **Reconstruction Estimate**: the customer summary, with trades, O&P-inclusive totals, plain-English bullets, exclusions and a 50/40/10 billing table.
- **Reconstruction Agreement**: the same scope, plus material selections, waivers, work-authorization terms and a signature block.
- **Xactimate Estimate**: always laid out like Forefront's real Xactimate exports (see "The Xactimate PDF" below), for the estimator, adjusters and customers who want line items. When the job has optional add-ons, also render a **"<Last Name> - Xactimate Estimate - For Insurance.pdf"** (see step 4).
- **Send-off email**: a Gmail draft in Hunter's voice, with the right PDF attached and the job's log address bcc'd (step 6).
- **Selections email**: once the price is agreed, a Gmail draft telling the homeowner what to pick and the budget per square foot for each (step 7). The Agreement is not sent until those picks are in.

Everything runs with the scripts in `scripts/` (Python + reportlab, already in the sandbox). Work in a scratch
folder and save finished files to the outputs folder (`/mnt/user-data/outputs` on claude.ai).

## Pick the path

- **New job**: a Homebase job page, a DocuSketch project, CompanyCam photos, notes. Do steps 0–6. A pasted Homebase
  job page ("Project name / Name / Phone / Email / Loss address") is the normal starting point: it gives the
  customer, the loss address, the customer email and the `office+<job#>` bcc address.
- **Convert an Xactimate PDF**: someone uploads an Xactimate estimate and wants the customer documents. Run
  `python scripts/read_xactimate.py estimate.pdf --json est.json` and confirm the summary says
  "all room totals match". Keep its items and prices as they are (`price_source: "xactimate"`), then do steps 3–6,
  rendering all three documents as usual (the Xactimate PDF is rebuilt in Forefront's layout from its items). Use the Xactimate's
  estimate name as `estimate_number`. While you have the line items in front of you, look for the slips an
  estimator would want caught before the customer sees a price: an install with no matching removal (new carpet
  but no carpet removal), a quantity far off the room size (1 SF of membrane on a 250 SF floor), a labor minimum
  triggered by such a slip, or $0 open/bid items. Don't change the Xactimate; mention them in the report.
- **Estimate agreed, what's next / selections / "send the agreement"**: the insurer approved the estimate (or an
  out-of-pocket homeowner said yes). Do step 7: the selections email comes next, and the Agreement only after the
  homeowner has picked.
- **Revise**: change the existing estimate.json and re-run step 4. Don't start over. If the user only needs one
  document right now ("I only need the estimate for now"), use `--only estimate`; otherwise render all three.

## 0. Pull the job's sketch and photos yourself

Don't ask Hunter to download and upload anything that can be fetched. Do both of these first, in this order,
and say in one line what came back (e.g. "DocuSketch: 1 floor, 6 scan positions. CompanyCam: 23 photos.").

### DocuSketch (built-in browser)

DocuSketch has no API or connector; the export is pulled through the **built-in browser** (the
`mcp__remote-devices__Claude_Browser__*` tools when the session is linked to Hunter's computer; load them all with
one ToolSearch on that prefix, and read the `built-in-browser` skill first).

1. `preview_start` with `https://app.docusketch.com`. If it answers that the site isn't allowed yet, call
   `request_access` for `https://app.docusketch.com` with scope `site`, then retry.
2. `get_page_text`. If it's the sign-in page, tell Hunter to sign in in the browser pane (never type credentials)
   and wait for "done". The sign-in persists, so this is a one-time step.
3. The Projects list (`/portal-cc/projects`) shows each project card with ID, name, floors, rooms, 360° image
   count and the buttons `Download sketch`, `Generate report`, `Download`, `Share`. Projects are usually named by
   last name only ("Williams"), sometimes `Name - address - city - Recon`. Find the card by name; if it isn't on
   page 1, use the page controls or the search box.
4. Trigger the downloads with `javascript_tool` so the click lands on the right card (every card has identical
   button labels, so `find` refs are ambiguous). Pattern:
   ```js
   // hook downloads so we can see what fired
   window.__cap=[]; const oo=XMLHttpRequest.prototype.open;
   XMLHttpRequest.prototype.open=function(m,u){window.__cap.push({m,u:String(u)});return oo.apply(this,arguments)};
   const oc=URL.createObjectURL; URL.createObjectURL=function(b){window.__cap.push({blob:b.size,type:b.type});return oc.apply(this,arguments)};
   // click "Download sketch" on the card that contains the project ID
   const b=[...document.querySelectorAll('button')].filter(x=>x.textContent.trim()==='Download sketch')
     .find(x=>{let c=x;for(let i=0;i<10&&c;i++){if(c.textContent.includes('<PROJECT ID>'))return true;c=c.parentElement}return false});
   b.click(); await new Promise(r=>setTimeout(r,4000)); window.__cap
   ```
   `Download sketch` downloads the sketches zip directly (an XHR to `.../sketch/order/<id>/get/sketches/pdf`, then
   a ~100–400 KB `application/octet-stream` blob). Then click the card's `Download` button the same way: a
   dialog opens with **Sketches** (Download all / Sketches / Sketches with measurements / Verisk (Xactimate)
   sketches), **Images** (Download all / 360° images / Cubic images), Scoping, Reports and Comments. Click
   **Images → Download all** (screenshot the dialog and click the link to the right of the "Images" heading);
   it fires `.../tour/<id>/images/all` and a zip of 20–70 MB. Wait ~6 s and check `window.__cap` for the blob.
5. The browser saves to Hunter's Downloads folder, not the workspace. Call `get_device_info`, request
   `~/Downloads` with `device_request_folder_access` (one request, reason "pick up the DocuSketch export"), then
   `device_list_dir` and `device_stage_files` on:
   - `Tour_<projectId>_Order_<orderId>_all_sketches<digits>.zip` (take the newest one; repeated clicks make
     duplicates with different digits)
   - `<projectId>_<Project name>_all_images.zip`
   They land under `/mnt/user-data/uploads/Downloads/`. Extract each zip into its own empty folder.
6. What's inside:
   - sketches zip: `<id>v2.ESX`, `common_<floor>.png/jpg`, `measurements_<floor>.png/jpg` (room name + L x W),
     `image_wall_measurements_<floor>.png/jpg` (every wall length, doors and windows). The ESX is normally the
     **encrypted** kind, so expect `read_esx.py` to say "no sketch found" and take measurements from the two plan
     images (see step 1). DocuSketch labels rooms by the scan-position name ("Master Bed", "Master Bed #2"...
     even when #4 is the bathroom and #5 is the hall), so rename rooms by what the photos show.
   - images zip: one equirectangular 360° JPG per scan position at the top level (`<Room> <floor>.JPG`,
     ~5 MB each) and six cube faces per position under `<floor>/<Room>/`. Downsize the panos to ~1600x800
     with PIL and view every one; they are the fastest way to see finishes, damage extent and what was pulled.
7. A DocuSketch share link (`app.docusketch.com/player/...`) is only the 360° viewer; use the project in the
   Projects list instead.

If the built-in browser isn't available (session not linked to his computer, or the tools can't reach the
desktop app), say so in one line and ask for the two zips.

### CompanyCam (connector)

Use the **CompanyCam connector** (`mcp__CompanyCam__*`), not the browser. Projects are named
`<job#> - <Last name> - <street> - <city> - <type>` (e.g. `3234 - Williams - 20021 E 48th Place - Denver - Recon`).

1. `search_projects` with the house number or job number (a last name like "Williams" matches dozens of unrelated
   projects and the result is huge). Note the project `id` and `photo_count`. Also look for a sibling mitigation
   project at the same address (`- WTR`, `- MIT`, `- Mold`): its photos show the pre-demo finishes. `photo_count`
   can read 0 right after a job is created; if it does, re-check before concluding there are no photos, and
   `list_projects` (newest first) shows the current counts.
2. `list_project_photos` with the project id. The result is large (3 KB per photo); when it's saved to a file
   instead of returned, parse it with Python and keep only `id`, `captured_at`, `creator_name`, `description` and
   the `web` URI per photo.
3. `view_photos` in batches of 10 ids (`variant: "web"`) and look at every photo. Note for the scope: what was
   removed (carpet strips, toe kick, baseboard, drywall cuts), materials and profiles, and anything the notes
   don't mention (dog damage, a different carpet on the stairs). Keep the photo ids: the adjuster photo report in
   step 6 is built from them.
4. Gallery links (`app.companycam.com/galleries/...`) still work in the browser when the connector isn't
   present: open the link, click a thumbnail, step through the lightbox. Never report that a link couldn't be
   used without trying.

What the photos can't show (a garage ceiling that wasn't scanned, baseboard quantities) is asked for in one
AskUserQuestion before pricing, since those answers move the number most. If Hunter is away, assume the typical
case (a 20' x 20' two-car garage, baseboard at the vanity/toilet only) and flag it.

## 1. Read the inputs

- **DocuSketch .ESX**: `python scripts/read_esx.py job.ESX --json rooms.json`. It prints floor SF, wall SF
  (minus doors and windows), floor and ceiling perimeter per room. DocuSketch exports every room at an 8' ceiling.
  If the user gave real heights, pass `--height "Kitchen=10"` (repeatable) or `--default-height 9`. If not, carry
  on at 8' and list it as an assumption, because walls change with height and floors don't.
- **Encrypted ESX** (the usual case now): read_esx.py says "no sketch found inside the ESX". Take the
  measurements from the floor-plan images in the same sketches zip (`measurements_<floor>.png` for room sizes,
  `image_wall_measurements_<floor>.png` for wall lengths): rooms are length x width, floor perimeter is 2 x (L +
  W), walls are perimeter x height minus doors and windows. Check the images are actually this property (room
  names and layout match the photos) before using them; a mismatched image has come through before. Watch for
  rooms whose labelled rectangles overlap (an L-shaped living/dining) or that include a stairwell (deduct the
  stair opening from a hall/landing), and don't count the overlap twice. Write the computed numbers into
  `rooms` in estimate.json by hand.
- **Photos**: for a zip or several images, run `python scripts/photo_sheets.py photos.zip --out photos/` and view
  the contact sheets. Open single `photo_###.jpg` files only where you need detail. Note what the photos show
  that matters for scope: materials, damage extent, texture, trim profile, cabinets, flooring type.
  CompanyCam projects usually include **before-loss photos** (furnished rooms); those settle the original
  finishes: flooring type and color, closet door style, wall texture, ceiling texture, mirrors, tub surround.
  Prefer what they show over guesses from post-demo photos.
- **Notes**: the estimator's notes say which rooms are affected and what's being done. They win over
  assumptions. Notes often arrive mid-task ("the homeowner also wants a price for..."); fold them in as options.
- **ITEL report**: a lab analysis (Itel Laboratories) the carrier orders on a damaged material, usually flooring:
  it names the sample it tested (e.g. "Bedroom 2 carpet"), the like-kind-and-quality replacement it matched, and
  a unit price. It arrives by email from the adjuster or ITEL; Keystone saves it in the job's `files/ITEL/` with a
  summary next to it. Read every ITEL report on the job before pricing, and use each one only for the material and
  rooms it covers (see "ITEL pricing" in step 2).
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
pricing a bid item or explaining a price. Run the lookups in one Bash loop and filter the output; the full
output of twenty lookups is too long to read.

**ITEL pricing.** When an ITEL report covers a material, that material's replacement line in the rooms the report
covers follows the report, not the price list:
- Keep the price-list description and unit for the line (e.g. the carpet or vinyl plank line), use the report's
  price as `unit_price`, set `price_source: "itel"`, and put the matched product and the report in the item note
  ("Priced per ITEL report 4412-883: Shaw Endura Plus, Amber Oak, $3.14/SF").
- ITEL prices are often material only, while price-list flooring lines are installed prices. When the report
  doesn't say it includes installation, ask before using its price on an installed line.
- Everything else stays priced as usual: removal, pad, underlayment, transitions, other materials, other rooms.
- Add the house-style sentence for it to that trade's notes ("Vinyl plank is priced per the ITEL flooring
  analysis at $3.14/SF.").
- Ask when it doesn't line up: the sample is a different material or room than the line, two reports cover the
  same material, or the report's unit doesn't convert cleanly (per SY vs per SF: 1 SY = 9 SF).

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
  A different carpet (color or style) on the stairs or in another room is a break, not continuous flooring.
  **The insurance Xactimate always carries the full continuous run in the base scope** (the adjuster has to
  say no to it); the line note says the carpet runs continuously with no seam or transition and is replaced
  through to the next break. When the homeowner asks for the rest of the floor priced separately so they can
  decide, the customer documents may show that part as an option, but the insurance Xactimate still includes it.
- **Doors**: bypass (sliding) and interior doors are not detached for drywall or paint work; detach & reset
  them only when flooring is being replaced under them.
- **Keep paint prep simple.** Don't list hardware detach & reset for painting (towel bars, mirrors, outlet and
  switch covers, thermostats, registers, recessed-light trims, fan covers, vanity lights). Masking covers
  that. Do keep electrical items that the drywall work itself requires, such as a recessed light in a removed
  ceiling section, or garage lights and the opener when a garage ceiling is replaced.
- **Texture**: price the texture that matches the existing surface (skim coat for smooth, machine/orange peel,
  knockdown), but the customer wording and line notes say "texture to match existing" — don't promise
  "smooth" or a specific finish.
- Basic masking goes in the room it protects, never in General Conditions.
- **Garage ceilings**: 5/8" drywall, batt insulation (R-30 unless told otherwise) even when the original was
  blown-in, tape joint at the perimeter, texture, PVA seal + two coats, detach & reset lights and the opener,
  contents large room, mask per SF. Leave the overhead door and track in place unless told otherwise, and ask.
- **Non-insurance extras** the homeowner asks about (pet damage, upgrades) are options on the customer
  documents and are left out of the insurance Xactimate.

## 3. Write the customer wording

Read `references/house_style.md`. Give every line item a `trade`, then write one `trades` entry per trade
(per option) with bullets in Forefront's wording and the standard note where one applies. Add `scopes` areas
and an `intro` only when there are optional add-ons. Agreements only: add `selections` when the user gives
product details (brand, product, SKU/color, size, photo). When the owner still has to pick finishes (flooring,
tile, doors, cabinets), add a `selections` entry per finish as an allowance: the owner's budget per unit (the
approved material cost plus O&P, less Forefront's material margin, see step 7), starting from
`price_lookup.py --components <words> --list <market>` (e.g. carpet: "Cut pile carpet - 36 oz." plus
"Carpet pad - rebond, 6 lb"; hand-entered costs such as snaplock laminate live in
`references/component_costs_manual.csv`), the quantity with waste, the allowance total, the pre-loss finish,
"Brand / product / color: To be selected by Owner", what happens over allowance, and `"viewed": "To be selected"`.

Signature blocks: the Reconstruction Agreement and any Material Selection Approval sheet carry only the
Customer / Homeowner signature block — no Forefront representative signature line.

## 4. Build the documents

Write `estimate.json` in the format in `references/estimate_format.md`, including the Xactimate fields:
`level` (e.g. "2nd Floor"), `type_of_estimate` (Water / Fire / Mold), `price_list`, `sketches` (the DocuSketch
floor-plan image per floor, preferably `image_wall_measurements_<floor>.png`), and `rooms` whose names match the
section names exactly. Rooms on another level (a garage or entry on the main level when the loss is upstairs)
get `"area": "Main Level"` on their section. Then:

```
python scripts/render.py estimate.json --out /mnt/user-data/outputs
```

The skill folder is read-only; copy `scripts/` and `assets/` to the scratch folder first and run from there,
which is also where the two edits below go.

Always produce all three documents - Reconstruction Estimate, Reconstruction Agreement and Xactimate Estimate - on
every job and every revision, and deliver all three to the estimator. The Agreement at this stage is a working
copy for Forefront: it never goes to the homeowner until the price is agreed and their selections are picked
(step 7). Use `--only` only when the user explicitly asks for just one
or two. Before reporting back, confirm the script printed three `->` lines. The script prints the totals by
trade; check that they look sane (no trade at $0, no missing trades, warnings about items without a trade).

**Selections sign-off**: when the owner needs to approve finishes before ordering (or asks for a selection sheet), fill `selections` in estimate.json as in step 3 and run `python scripts/render.py estimate.json --out <dir> --only selections`. It writes `<Last Name> - Material Selection Approval.pdf`: each selection with an owner-initials line, the selection acknowledgments from company.json, and the customer signature block only. It is separate from the three documents and isn't sent unless asked.

**Insurance Xactimate.** When estimate.json has option sections, also write `estimate_insurance.json` from it:
drop the non-insurance options (pet damage, upgrades) and their trades; fold any continuous-flooring option into
the base scope (`option: ""`) with adjuster-facing notes; clear `scopes` and `intro`. Render it with
`--only xactimate` into a separate folder and save it as `<Last Name> - Xactimate Estimate - For Insurance.pdf`.
That is the file the adjuster gets; the full Xactimate (with the options labelled) stays for Hunter. Keep
`estimate_insurance.json` in the outputs too.

Markup applies to the Estimate and Agreement only, using `markup_pct` from `assets/company.json` unless the
user gives one or estimate.json sets it ("bump it up by 15%" = `"markup_pct": 15`). Say which markup you used.

### Customer-document layout rules

- **Never print the "All amounts include overhead and profit" note** (company.json `amounts_note`) on the
  Estimate or Agreement. render.py still has the line
  `story.append(Paragraph(esc(company.get("amounts_note", "")), ...))` in the estimate builder; delete it from
  the scratch copy before rendering.
- **A short estimate goes on one page.** The Job Total & Billing block may sit at the very bottom of page 1:
  use a 0.3" bottom margin with the footer at 0.12", H2 spaceBefore 6 on that heading, 3pt table padding and
  1pt spacers in the exclusions list. Rasterize (`pdftoppm -r 60 -png`) and confirm the page count. An
  estimate with two options runs three pages; that's fine.
- The logo in `assets/logo.png` is 800px wide and makes up most of the PDF's bytes. Before rendering, shrink the
  scratch copy to 260px wide and 64 colors (`im.thumbnail((260,40)); im.quantize(64).convert("RGBA")`); it
  renders identically on screen and keeps the estimate PDF under ~10 KB, which matters for emailing (step 6).

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

After rendering, look at a few pages (`pdftoppm -r 60 -png`, tile 3–4 pages into one image with PIL to save
reads) to confirm nothing landed in the wrong group.

### File names

render.py names the documents by the customer's last name: `<Last Name> - Reconstruction Estimate.pdf`,
`<Last Name> - Reconstruction Agreement.pdf` and `<Last Name> - Xactimate Estimate.pdf`; add
`<Last Name> - Xactimate Estimate - For Insurance.pdf` when there are options.

## 5. Report back

Keep it short; the estimator reads this between jobs. Cover:
1. The documents created.
2. The total, plus optional add-ons, and the insurance Xactimate total when it differs.
3. Items priced without price-book history.
4. Assumptions, especially 8' ceilings, rooms left out and anything not captured by DocuSketch/CompanyCam.
5. Your questions: the few (about 3) whose answers would change the price most, with a rough dollar swing each.
   Fold the minor ones into the assumptions instead of asking.

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
  the job in Homebase. The job number is also the prefix of the CompanyCam project name. Ask for it if neither
  is available.
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
> <options paragraph, only when there are add-ons: one short paragraph naming each option and its price, and
> that neither is in the total unless they want it>
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
- *Homeowner, insurance claim* (Hunter says it "needs an Xact for insurance"): say the Xactimate version has
  gone / will go to the adjuster once he has the claim number and contact, that the adjuster's approval is the
  next step, and that the deductible is due at signing. Mention that supplements can change the number if the
  adjuster's scope differs.
- *Homeowner, out of pocket*: no insurance talk; mention the 50/40/10 billing schedule. Don't promise the
  Agreement yet: say that once they're happy with the number, the next step is picking their finishes, and the
  Agreement follows (step 7).
- *Adjuster*: professional and brief. Insured name, loss address, claim number, price list used, a 2–3 line
  summary of the scope logic (why the walls are included, why the carpet runs through, texture to match,
  anything unusual) and a request to review/approve or call. Never mention markup. Attach the **For Insurance**
  Xactimate Estimate **and a photo report** (key CompanyCam photos with a one-line description each); the
  Reconstruction Estimate and the homeowner options are not for adjusters. Homeowner cc only if Hunter says so.
  Only draft it once there is an adjuster contact.

**Attachments**: homeowner gets the Reconstruction Estimate only (not the Agreement unless asked); adjuster gets
the Xactimate Estimate + photo report. The Gmail connector takes attachments as inline base64, which has to be
typed into the tool call, so:
1. Shrink first: render with the 260px logo, then `qpdf --recompress-flate --compression-level=9
   --object-streams=generate in.pdf small.pdf` (aim for under ~10 KB / 13k base64 chars). Copy `small.pdf` over
   the delivered estimate PDF so the file in outputs is the one that was emailed.
2. `base64 -w0 small.pdf > est.b64`, then `fold -w 1300 est.b64 | split -l 1 -d - chunk_` and `cat` the chunks
   (about 10 of them, in two Bash calls).
3. Re-type the whole string in a Bash heredoc, `tr -d '\n'`, and `cmp` it against `est.b64`; also `base64 -d`
   it and `cmp` against the PDF. A mismatch is usually one inserted or dropped character: find the first
   differing index with Python, print 20 chars either side from both files, fix it with `sed` on the typed
   copy, and re-verify. Only when both match, pass the same string as `attachments[0].content`
   (`mimeType: application/pdf`, `filename: "<Last Name> - Reconstruction Estimate.pdf"`).
4. A decode error from the connector means a transcription slip — don't resend blind; re-verify.
Files too big for that path (Xactimate PDFs with sketches, photo reports): save them to the outputs folder and
attach through Claude in Chrome (`file_upload` into the Gmail compose's file input, which accepts files from the
session's outputs folder) when the extension is connected (`list_connected_browsers` returns it); otherwise
create the draft without them and tell Hunter exactly which file to drag on.

Report the draft in one line (recipient, bcc, subject, what's attached, what still needs attaching).

## 7. After the price is agreed: selections first, then the Agreement

Forefront's order is fixed, and the Agreement never goes out early:

1. Estimate sent (step 6).
2. Price agreed: the adjuster approves the Xactimate (insurance jobs), or the homeowner says yes (out of pocket).
3. **Selections email** to the homeowner: what they need to pick and the budget for each.
4. Homeowner picks. Record each pick in `selections` in estimate.json (brand, product, color, price).
5. Reconstruction Agreement rendered with those selections and sent for signature; deposit and scheduling follow.

So when someone asks "what's next" on an approved job, or asks for the Agreement before the picks are in, draft
the selections email instead and say why. A job with nothing for the owner to choose (drywall and paint to match
existing only) skips steps 3-4; say so rather than inventing selections.

**What goes on the list.** Every finish in the agreed estimate that the owner has to choose: flooring (wood,
laminate, vinyl, carpet, tile), wall tile, cabinets, countertops, doors, fixtures, and paint colors where a
surface is being repainted. Things matched to existing (texture, baseboard profile, ceiling tile, trim paint)
are not selections; name them in one sentence so the owner knows there is nothing to pick there.

**The budget** is what the owner may spend per unit on the material. It is NOT the approved material price.
The math, always in this order:

1. Start from the approved material price per unit (below).
2. Add O&P, because the insurer pays O&P on the material too: x (1 + overhead + profit), 20% at Forefront
   (`overhead_pct` + `profit_pct` in `assets/company.json`).
3. Take out Forefront's material margin: x (1 - `material_margin_pct`), 30% unless Hunter gives another.
4. Round down to the cent.

$5.51 approved -> $6.61 with O&P -> $4.62 budget. `python scripts/price_lookup.py --budget 5.51` prints it.

The approved material price it starts from:
- An ITEL report covers the material: its per-SF price ("Shaw Albright, 5" oak, $5.51/SF").
- Otherwise: the material component for the grade in the estimate line, from
  `price_lookup.py --components <words> --list <market>` (e.g. "Carpet - High grade" -> "Carpet - High grade -
  Allowance"; "Tile floor covering" at average grade -> "Ceramic/porcelain floor tile"; hand-entered costs are in
  `references/component_costs_manual.csv`). Never start from the installed line price; it includes labor.
- If the adjuster approved a different grade or price than Forefront wrote, start from what was approved.

Rules for the number the owner sees:
- Only the budget goes in the email and in the Agreement's `selections` allowance. Never show the approved
  price, the margin, or how the budget was worked out, and never call the budget "what insurance approved".
  Call it "your material budget".
- The budget is the shelf price before sales tax. Forefront pays the tax, so the real margin lands a little
  under the target; if Hunter wants the margin held after tax, divide the budget by (1 + the local rate).
- Pad, underlayment, setting materials and grout are included in the job and are not part of the budget; say so.
- In the report to Hunter (not the email), list approved price -> budget for each selection, and flag any line
  where the owner has already been shown the approved material price (an ITEL price in an Xactimate note they
  were copied on), since they may ask about the difference.

For each selection give: where it goes, the like-kind product or grade, the budget per SF (per LF / EA
where that is the unit), and the area being covered so they can tell a supplier how much (floor SF; mention that
Forefront orders the waste). Paint colors have no budget: ask for the color name/brand or offer to color match.

**The email** is a Gmail draft like step 6 (Forefront account, signature on, bcc `office+<job#>`, never sent).
Subject: `Selections for your repairs – <street address>`. Hunter's voice: open with the news that the estimate
is agreed, say that picking finishes is the next step, then one short paragraph per selection (plain sentences,
no table), then what happens when they go over or under budget (over: we price the difference before ordering
and it is the owner's cost; nothing is ordered until they approve), how to send picks back (reply with brand,
product, color and a link or photo, or ask to see samples), and what comes after (the Agreement with their
selections written in, then deposit and scheduling). Do not attach the Agreement and do not ask for a signature
or deposit in this email. Leave out supplements, markup and anything about payment of other invoices.

When the picks come back, fill `selections`, re-render (`--only agreement`, plus `--only selections` when a
Material Selection Approval sheet is wanted), and draft the Agreement email.

## Company details

`assets/company.json` holds Forefront's name, address, billing schedule, exclusions, waivers, agreement
terms, default markup, and the `"xactimate"` block (letterhead, estimator details, cover wording, IICRC line);
`assets/logo.png` is the customer-document logo and `assets/xact_logo.png` the Xactimate letterhead logo.
`references/price_book.csv` is generated from Forefront's past Xactimate estimates (no customer data) by
`py -m estimator build-skill` on the estimating PC. `references/xactimate_prices.csv` (every line item on the
current Xactimate price list, REMOVE and REPLACE split) and `references/component_costs.csv` come from
`py -m estimator import-pricelist <items.pdf> --components <components.pdf>`. Re-uploading the rebuilt skill
refreshes prices.