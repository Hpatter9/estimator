"""Core data shapes shared by importers, the generator and exporters."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    category: str = ""  # Xactimate-style category code, e.g. "DRY", "PNT", "WTR"
    selector: str = ""  # Xactimate-style selector, e.g. "1/2", "SP"
    description: str
    quantity: float = 0.0
    unit: str = "EA"  # SF, LF, SY, EA, HR, ...
    unit_price: float = 0.0
    tax: float = 0.0
    note: str = ""
    price_source: str = ""  # "history", "ai", "manual" - lets you see what to double-check

    @property
    def extended(self) -> float:
        """Quantity x unit price, before tax."""
        return round(self.quantity * self.unit_price, 2)

    @property
    def total(self) -> float:
        return round(self.extended + self.tax, 2)


class Room(BaseModel):
    name: str
    length_ft: Optional[float] = None
    width_ft: Optional[float] = None
    height_ft: Optional[float] = None
    floor_sf: Optional[float] = None
    ceiling_sf: Optional[float] = None
    wall_sf: Optional[float] = None
    perimeter_lf: Optional[float] = None
    notes: str = ""


class Section(BaseModel):
    """A group of line items - usually one room/area."""
    name: str
    room: Optional[Room] = None
    items: list[LineItem] = Field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return round(sum(i.total for i in self.items), 2)


class Estimate(BaseModel):
    title: str = ""
    customer: str = ""
    address: str = ""
    claim_number: str = ""
    loss_type: str = ""  # water, fire, mold, storm, remodel...
    estimate_date: date = Field(default_factory=date.today)
    summary: str = ""
    sections: list[Section] = Field(default_factory=list)
    overhead_pct: float = 10.0
    profit_pct: float = 10.0
    tax_pct: float = 0.0
    source_file: str = ""

    @property
    def line_item_total(self) -> float:
        """Sum of quantity x unit price, before tax and O&P."""
        return round(sum(i.extended for _, i in self.all_items()), 2)

    @property
    def overhead(self) -> float:
        return round(self.line_item_total * self.overhead_pct / 100, 2)

    @property
    def profit(self) -> float:
        return round(self.line_item_total * self.profit_pct / 100, 2)

    @property
    def sales_tax(self) -> float:
        """Per-line taxes plus the estimate-wide tax percentage."""
        item_tax = sum(i.tax for _, i in self.all_items())
        return round(item_tax + self.line_item_total * self.tax_pct / 100, 2)

    @property
    def grand_total(self) -> float:
        return round(self.line_item_total + self.overhead + self.profit + self.sales_tax, 2)

    def all_items(self):
        for s in self.sections:
            for i in s.items:
                yield s, i
