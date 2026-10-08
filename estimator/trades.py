"""Trades used on the customer Reconstruction Estimate / Agreement, in the order they print,
plus the standard note under each trade and a keyword fallback for assigning line items.

The AI step (customer.py) assigns trades and writes the bullets; guess_trade() is used when
there is no AI (offline) or for items added by hand.
"""
from __future__ import annotations

import re

from .models import Estimate, LineItem

TRADE_ORDER = [
    "Demolition & General Conditions",
    "Insulation",
    "Drywall",
    "Cabinetry & Vanities",
    "Plumbing / Shower",
    "Electrical",
    "Flooring",
    "Finish Carpentry / Trim",
    "Appliances",
    "Painting",
    "Customer Selections",
]

DEFAULT_NOTES = {
    "Demolition & General Conditions": "Construction cleaning is a general cleanup of the work areas done daily as work "
                                       "progresses. It is not a deep clean.",
    "Drywall": "Texture is matched to blend with the existing surface. An exact match is not always achievable on a "
               "repair, and there can be some variation between new and existing texture.",
    "Plumbing / Shower": "Supply lines are replaced when they are disturbed so old seals don't dry out and leak later.",
    "Flooring": "Installed per manufacturer instructions, including requirements at vanities and fixed objects.",
    "Customer Selections": "Materials as documented in the Material Selections section of this Agreement.",
}

# (trade, pattern) - checked in order; first match wins
STRONG = [
    ("Appliances", r"range hood|dishwasher|refrigerator|\brange\b|washer|dryer|microwave|appliance"),
    ("Plumbing / Shower", r"sink|faucet|angle stop|supply line|p-trap|disposer|toilet|\btub\b|bathtub|shower|drain|"
                          r"flange|plumb|water heater|valve|tub surround"),
    ("Electrical", r"outlet|switch|light fixture|light bar|electric|exhaust fan|ceiling fan|smoke detector|wiring"),
    ("Cabinetry & Vanities", r"cabinet|countertop|vanity|backsplash|knob or pull"),
    ("Insulation", r"insulation"),
]
GROUPS = {
    "paint": "Painting", "drywall": "Drywall", "insulation": "Insulation", "electrical": "Electrical",
    "casing": "Finish Carpentry / Trim", "door": "Finish Carpentry / Trim", "trim": "Finish Carpentry / Trim",
    "finish carpentry": "Finish Carpentry / Trim", "baseboard": "Finish Carpentry / Trim",
    "cleaning": "Demolition & General Conditions", "general": "Demolition & General Conditions",
    "floor": "Flooring", "carpet": "Flooring", "tile floor": "Flooring", "plumbing": "Plumbing / Shower",
    "cabinet": "Cabinetry & Vanities", "appliance": "Appliances",
}
WEAK = [
    ("Painting", r"paint|seal/prime|primer|stain|mask and prep for paint|mask the floor"),
    ("Drywall", r"drywall|texture|tape joint|popcorn|mask wall|heat/ac register|firetap"),
    ("Flooring", r"carpet|\bpad\b|vinyl plank|tile floor|hardwood|oak flooring|underlayment|t-mold|reducer|"
                 r"stair nosing|floor prep|floor leveling|wood floor"),
    ("Finish Carpentry / Trim", r"baseboard|casing|door|base shoe|quarter round|trim|shelving|shelf|crown|molding"),
    ("Demolition & General Conditions", r"haul|debris|dumpster|clean|supervision|protect|dust|contain|contents|"
                                        r"labor minimum|permit|delivery"),
]


def guess_trade(item: LineItem) -> str:
    text = item.description.lower()
    for trade, pat in STRONG:
        if re.search(pat, text):
            return trade
    group = item.group.lower()
    for key, trade in GROUPS.items():
        if key in group:
            return trade
    for trade, pat in WEAK:
        if re.search(pat, text):
            return trade
    return "Demolition & General Conditions"


def fill_missing_trades(est: Estimate) -> None:
    for _, item in est.all_items():
        if not item.trade:
            item.trade = guess_trade(item)


def trade_sort_key(trade: str) -> tuple[int, str]:
    base = trade.split(" — ")[0]
    return (TRADE_ORDER.index(base) if base in TRADE_ORDER else len(TRADE_ORDER) - 1, trade)
