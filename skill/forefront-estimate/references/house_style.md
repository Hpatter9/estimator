# Forefront house style: customer scope (Reconstruction Estimate / Agreement)

The customer documents group the Xactimate line items into **trades**, each with an O&P-inclusive total,
plain-English **bullets**, and sometimes a short **note**. A homeowner should understand every bullet without
knowing Xactimate.

## Trades, in print order

Demolition & General Conditions · Insulation · Drywall · Cabinetry & Vanities · Plumbing / Shower (or just
"Plumbing" when there is no shower or tub work) · Electrical · Flooring (name the material when there's one:
"Flooring — Luxury Vinyl Plank", "Flooring — Carpet"; two materials = two trades) · Finish Carpentry / Trim ·
Appliances · Painting · Customer Selections (Agreements only, for materials the customer picked)

Assign every line item to exactly one trade, where a homeowner would expect it, not where Xactimate grouped it:
- sinks, faucets, angle stops, supply lines, P-traps, disposers, toilets, tubs, shower valves, drains → Plumbing
- range hood, dishwasher, refrigerator, range, washer/dryer detach & reset → Appliances
- casing, doors, door knobs, baseboard, quarter round, shelving, trim boards → Finish Carpentry / Trim
- haul debris, final cleaning, supervision, contents moving/protection, dust containment, labor minimums
  that aren't clearly one trade → Demolition & General Conditions
- masking for drywall → Drywall; masking/protection for painting → Painting
- floor prep, underlayment, transitions, stair nosing → the matching Flooring trade

## Bullets

- Short, start with a verb, no Xactimate codes, quantities or units.
- One bullet per kind of work, even when it appears in several rooms ("Install outlets", not one per room).
- Add " — Room" (em dash) only when the work is limited to particular areas and that matters to the customer:
  "Install new carpet — Basement and Basement Stairs", "Patch drywall damaged when baseboard was pulled — Basement".
- Mention material and size when it matters: "Install new baseboard — 3 1/4\" MDF, flat profile".
- Fold small prep items into one bullet: masking + floor protection for drywall becomes
  "Mask walls and protect floors and surrounding finishes during drywall work".
- Detach & reset is written "Detach and reset …"; R&R is "Replace …"; Remove/Install as written.

## Notes under a trade (only when one applies)

Standard notes, used word for word:
- Demolition & General Conditions: "Construction cleaning is a general cleanup of the work areas done daily as work progresses. It is not a deep clean."
- Drywall: "Texture is matched to blend with the existing surface. An exact match is not always achievable on a repair, and there can be some variation between new and existing texture."
- Plumbing: "Supply lines are replaced when they are disturbed so old seals don't dry out and leak later." (add "and angle stops" when those are replaced too)
- Flooring (Agreement): "Installed per manufacturer instructions, including requirements at vanities and fixed objects."
- Customer Selections: "Materials as documented in the Material Selections section of this Agreement."

Add one job-specific sentence when the estimator's line-item notes give a reason the customer should know,
e.g. "Popcorn ceiling texture is blended in rather than scraped, which avoids a second round of abatement." or
"Vinyl plank is priced per the ITEL flooring analysis at $3.14/SF."

## Optional add-ons

When part of the work is priced separately (e.g. a pantry the customer may or may not want), those sections get
`"option": "Pantry Repairs"`. Then write `intro` like:
"How this estimate is organized. The Base Scope covers all repairs except the pantry. The pantry repairs are
priced separately as an optional add-on and are not part of the Total Job Price unless accepted."
and `scopes` areas like "Kitchen, Living Room, Hallway and closets, HVAC, Bathroom, and Bedroom 1 and closet".
Without optional add-ons leave `intro` empty.

## Real examples

### Xactimate line items → bullets (same job)

| Xactimate | Customer bullet |
|---|---|
| Mask wall - plastic, paper, tape (per LF); Mask per square foot for drywall work | Mask walls and protect floors and surrounding finishes during drywall work |
| 1/2" drywall - hung, taped, ready for texture | Replace damaged drywall — 1/2", hung, taped, ready for texture |
| Tape joint for new to existing drywall - per LF | Tape joints where new drywall meets existing |
| Texture drywall - machine | Texture to match existing |
| Acoustic ceiling (popcorn) texture | Blend acoustic (popcorn) ceiling texture |
| Heat/AC register - Mechanically attached - Detach & reset | Detach and reset heat/AC registers for drywall work |
| R&R Angle stop valve | Replace angle stop valves |
| R&R Plumbing fixture supply line | Replace supply lines |
| Garbage disposer - Detach & reset | Detach and reset garbage disposer |
| R&R P-trap assembly - ABS (plastic) | Replace P-traps |
| Install Cabinetry - lower (base) units | Install base cabinets |
| Install Countertop - flat laid plastic laminate | Install plastic laminate countertop |
| Casing - 2 1/4" | Install door casing — 2 1/4" |
| Bypass (sliding) door set - Install | Install bypass (sliding) closet door sets |
| Install Range hood | Install range hood (under Appliances) |
| Final cleaning - construction - Residential | Final construction cleaning |
| Haul debris - per pickup truck load - including dump fees | Haul debris and dump fees |

### A finished scope (water loss, two floors)

**Demolition & General Conditions**
- Haul debris and dump fees
- Final construction cleaning — Main Floor and Basement
- Move contents out of work areas and back — affected areas
*Construction cleaning is a general cleanup of the work areas done daily as work progresses. It is not a deep clean.*

**Drywall**
- Protect floors during drywall work — Basement
- Patch drywall damaged when baseboard was pulled — Basement
- Texture patches to match existing — Basement

**Plumbing**
- Remove and reset toilet — Bathroom/Laundry Room
- Replace supply line — Bathroom/Laundry Room

**Flooring — Luxury Vinyl Plank**
- Remove damaged vinyl plank flooring — all continuous flooring
- Floor prep for new flooring — all continuous flooring
- Install new luxury vinyl plank flooring — all continuous flooring
- Protect new flooring for the rest of the project — all continuous flooring
- Replace stair nosing — Main Floor Stairs and Main Room

**Flooring — Carpet**
- Remove damaged carpet — Basement and Basement Stairs
- Remove and replace carpet pad — Basement and Basement Stairs
- Install new carpet — Basement and Basement Stairs
- Waterfall-style carpet install on 13 steps — Basement Stairs

**Finish Carpentry / Trim**
- Replace quarter round — Kitchen/Dining and Main Room
- Install new baseboard — 4 1/4" MDF, flat profile — Kitchen/Dining and Living Room
- Detach and reset baseboard — affected areas

**Appliances**
- Remove and reset dishwasher, refrigerator, and range — Kitchen/Dining
- Remove and reset dryer and washer — Bathroom/Laundry Room

**Painting**
- Mask, prep, and paint baseboard — affected areas
- Cover contents with plastic during painting — Basement
- Paint walls — one coat — Basement
- Seal/prime and paint drywall patches — Basement
