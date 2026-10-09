# estimate.json - what render.py reads

One file holds the whole job: the Xactimate-style line items (by room) plus the customer-facing wording.

```json
{
  "customer": "Jane Doe",
  "address": "123 Main St, Denver, CO 80211",
  "estimate_number": "DOE_123_REC",
  "date": "2026-10-09",
  "claim_number": "",
  "intro": "",
  "markup_pct": null,
  "overhead_pct": 10,
  "profit_pct": 10,
  "tax_pct": 0,

  "rooms": [
    {"name": "Kitchen", "height_ft": 8, "floor_sf": 153.36, "wall_sf": 362.91, "floor_perimeter_lf": 46.29}
  ],

  "sections": [
    {"name": "General Conditions", "option": "", "items": [
      {"description": "Haul debris - per pickup truck load - including dump fees", "quantity": 1, "unit": "EA",
       "unit_price": 211.64, "trade": "Demolition & General Conditions", "price_source": "price_book"}
    ]},
    {"name": "Kitchen", "option": "", "items": [
      {"description": "1/2\" drywall - hung, taped, ready for texture", "quantity": 187, "unit": "SF",
       "unit_price": 2.72, "trade": "Drywall", "price_source": "price_book",
       "note": "2 ft flood cut x 46.29 LF, rounded up to full sheets"}
    ]},
    {"name": "Pantry", "option": "Pantry Repairs", "items": []}
  ],

  "trades": [
    {"trade": "Drywall", "option": "", "bullets": [
      "Mask walls and protect floors and surrounding finishes during drywall work",
      "Replace damaged drywall — 1/2\", hung, taped, ready for texture"],
     "note": "Texture is matched to blend with the existing surface. An exact match is not always achievable on a repair, and there can be some variation between new and existing texture."}
  ],
  "scopes": [{"option": "", "areas": "Kitchen and Hallway"}, {"option": "Pantry Repairs", "areas": "Pantry"}],

  "selections": [
    {"title": "Vinyl Plank Flooring — Bathroom",
     "fields": [["Brand", "DuraLux Performance (Floor & Decor)"], ["Product", "Lorraine Sienna LVP"],
                ["SKU / Color", "101058436 / Beige"], ["Size", "7 in x 48 in, 5 mm"]],
     "image": "/path/to/photo.jpg", "caption": "DuraLux Lorraine Sienna — Beige",
     "viewed": "Online only (not viewed in person)"}
  ],
  "questions": ["Is the carpet pad wet, or only the carpet?"]
}
```

## Fields

- **sections**: one per room (plus "General Conditions"). `option` is "" for the base scope, or the name of
  an optional add-on priced separately. Every item needs `description`, `quantity`, `unit`, `unit_price` (per
  unit, before O&P) and `trade` (see house_style.md). Optional: `tax`, `note`, `price_source`
  ("price_book", "estimated", or "xactimate" when it came from an existing Xactimate PDF).
- **trades**: the customer bullets, one entry per trade per option. A trade without an entry falls back to its
  line-item descriptions, which reads badly, so write one for every trade that has items.
- **scopes**: the "areas" line under Base Scope / each optional add-on (only printed when there are add-ons).
- **intro**: the "How this estimate is organized." box; leave "" unless there are optional add-ons.
- **markup_pct**: null uses the company default from assets/company.json. Applies to the customer documents
  only; the Xactimate-style PDF is at price-book prices.
- **selections**: optional; only the Agreement prints them. Leave out when there are none.
- **rooms**: optional; adds dimensions to the Xactimate-style PDF. Paste from `read_esx.py --json`.
- **estimate_number**: printed under JOB on the Estimate. Use the Xactimate estimate name when there is one
  (e.g. SMITH_123_REC), otherwise LASTNAME_STREETNUMBER_REC.

## Totals (render.py does all the math)

- O&P per line = extended × (overhead + profit), rounded per line like Xactimate.
- Trade total on the customer documents = sum of line totals with O&P × (1 + markup).
- Scope total = sum of its trade totals. Billing = 50% / 40% / 10% (company.json), rounded half-up, the final
  payment takes the remainder.
