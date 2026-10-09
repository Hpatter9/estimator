# Scoping a reconstruction job the Forefront way

The Xactimate-style line items are the backbone: they set quantities and prices, and the customer documents are
built from them. Write them in Xactimate wording, using items from the price book wherever one fits.

## Quantities from the DocuSketch measurements (read_esx.py)

| Work | Quantity |
|---|---|
| Wall drywall, texture, paint (full height) | Wall SF (already minus doors/windows) |
| Flood cut / partial-height drywall | Floor perimeter LF × cut height, or the "per LF - up to 2' tall" items in LF |
| Ceiling drywall/texture/paint | Ceiling SF (= floor SF) |
| Flooring, floor prep, underlayment, floor protection, final cleaning | Floor SF |
| Baseboard, quarter round, base shoe | Floor perimeter LF |
| Masking walls (per LF) | Ceiling perimeter LF |

- DocuSketch exports every room at an 8' ceiling. If the user gives real heights, re-run `read_esx.py` with
  `--height "Room=10"`; walls change, floors don't. If you don't know, say in the questions that heights were
  assumed at 8'.
- Only scope rooms the notes/photos say are affected. Large sketches include the whole house.
- Flooring that runs continuously into unaffected rooms usually has to be replaced through to a break (doorway,
  transition) — scope the continuous area and say so in a line-item note.
- Use measured quantities; don't add waste on top unless the price-book item is a waste-free material item and
  past jobs added it. Mention any unusual waste (pattern matching, diagonal installs) in a line-item note.
- Round quantities sensibly (SF to whole numbers or the measured 2 decimals as past estimates do; LF to 2 decimals).

## Items Forefront usually includes

**General Conditions** (its own section, not a room): haul debris (per pickup truck load), residential
supervision/project management when the job warrants it, dust containment for sanding, delivery fees for
materials that need acclimation (wood).

**Each affected room**, as applicable:
- Drywall: mask wall (per LF), mask per SF for drywall work, drywall (hung, taped, ready for texture), tape joint
  for new to existing (per LF), texture to match, PVA primer before texture on skim coat areas.
- Painting: mask/prep for paint, mask the floor, seal/prime then paint repaired area (two coats on patches),
  paint the rest of the affected wall/ceiling one coat, paint baseboard.
- Trim: detach & reset or replace baseboard/casing as the notes say; quarter round with flooring.
- Plumbing near any cabinet/vanity/toilet that's disturbed: R&R angle stops and supply lines, P-trap, detach &
  reset or reinstall fixtures.
- Final cleaning - construction - Residential (floor SF of the room).
- Contents: protect/cover or move out and back.

Labor minimums appear when a trade's work is very small; Xactimate adds them. Add one only if past estimates
for similar small scopes did.

## Prices

1. Search the price book: `python scripts/price_lookup.py <words> [--unit SF]`. The most-used items are listed in
   `references/common_items.md`.
2. Use the item's description and unit exactly, and its `median_price` (per unit, before O&P).
   `price_source: "price_book"`.
3. If nothing in the price book fits, estimate a realistic Denver-area Xactimate price, set
   `price_source: "estimated"`, and list it for the user to check. Never present an estimated price as history.

## When the scope is unclear

Scope the most likely option, keep going, and add a plain question to `questions` (e.g. "Is the carpet pad wet,
or only the carpet?"). Don't invent damage the notes, photos and measurements don't show.

## Photos

Look at the contact sheets (`photo_sheets.py`) before scoping. Use them to confirm materials (flooring type,
texture, baseboard profile, cabinet type), the extent of damage, and anything the notes don't mention — and
say what you saw that changed the scope.
