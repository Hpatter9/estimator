"""Core data shapes shared by importers, the generator and exporters."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, Field


def r2(x: float) -> float:
    """Round money half-up to cents (how Xactimate and the billing schedule round)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class LineItem(BaseModel):
    category: str = ""  # Xactimate category code, e.g. "DRY", "PNT", "WTR"
    selector: str = ""  # Xactimate selector, e.g. "1/2", "SP"
    description: str
    quantity: float = 0.0
    unit: str = "EA"  # SF, LF, SY, EA, HR, ...
    unit_price: float = 0.0  # per unit, before tax and O&P (reset + remove + replace)
    tax: float = 0.0
    note: str = ""
    group: str = ""  # Xactimate group heading the item was under ("Drywall", "Cabinets & Sink")
    trade: str = ""  # trade on the customer estimate ("Plumbing / Shower", "Finish Carpentry / Trim")
    customer_text: str = ""  # plain-English bullet for the customer estimate
    price_source: str = ""  # "history", "ai", "manual" - lets you see what to double-check

    @property
    def extended(self) -> float:
        """Quantity x unit price, before tax and O&P."""
        return r2(self.quantity * self.unit_price)

    @property
    def total(self) -> float:
        """Before O&P."""
        return r2(self.extended + self.tax)

    def op(self, op_pct: float) -> float:
        return r2(self.extended * op_pct / 100)

    def total_with_op(self, op_pct: float) -> float:
        return r2(self.total + self.op(op_pct))


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
    option: str = ""  # "" = base scope; otherwise the name of an optional add-on ("Pantry Repairs")
    items: list[LineItem] = Field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return r2(sum(i.total for i in self.items))


class SelectionField(BaseModel):
    label: str
    value: str


class MaterialSelection(BaseModel):
    """A customer selection shown in the Agreement's Material Selections section."""
    title: str  # "Vinyl Plank Flooring — Bathroom"
    fields: list[SelectionField] = Field(default_factory=list)  # BRAND, PRODUCT, SKU / COLOR, SIZE, ...
    image_path: str = ""
    caption: str = ""
    viewed: str = "Online only (not viewed in person)"


class TradeText(BaseModel):
    """Customer-facing wording for one trade on the Reconstruction Estimate / Agreement."""
    trade: str
    option: str = ""  # "" = base scope
    bullets: list[str] = Field(default_factory=list)
    note: str = ""


class ScopeText(BaseModel):
    option: str = ""  # "" = base scope
    areas: str = ""  # "Kitchen, Living Room, Hallway and closets, ..."
    description: str = ""


class Estimate(BaseModel):
    title: str = ""
    estimate_numbers: list[str] = Field(default_factory=list)  # shown under JOB on your templates
    customer: str = ""
    address: str = ""
    claim_number: str = ""
    loss_type: str = ""  # water, fire, mold, storm, remodel...
    price_list: str = ""
    estimate_date: date = Field(default_factory=date.today)
    summary: str = ""
    intro: str = ""  # "How this estimate is organized." box on the customer estimate
    sections: list[Section] = Field(default_factory=list)
    selections: list[MaterialSelection] = Field(default_factory=list)
    trade_text: list[TradeText] = Field(default_factory=list)
    scope_text: list[ScopeText] = Field(default_factory=list)
    overhead_pct: float = 10.0
    profit_pct: float = 10.0
    tax_pct: float = 0.0
    source_file: str = ""

    @property
    def op_pct(self) -> float:
        return self.overhead_pct + self.profit_pct

    def all_items(self, option: str | None = None):
        for s in self.sections:
            if option is None or s.option == option:
                for i in s.items:
                    yield s, i

    @property
    def options(self) -> list[str]:
        """Names of optional add-on scopes, in order."""
        seen: list[str] = []
        for s in self.sections:
            if s.option and s.option not in seen:
                seen.append(s.option)
        return seen

    # ----- totals (base scope only; optional add-ons are priced separately) -----
    def _items(self, option: str = ""):
        return [i for _, i in self.all_items(option)]

    def scope_line_total(self, option: str = "") -> float:
        return r2(sum(i.extended for i in self._items(option)))

    def scope_op(self, option: str = "") -> float:
        """O&P summed per line, like Xactimate."""
        return r2(sum(i.op(self.op_pct) for i in self._items(option)))

    def scope_tax(self, option: str = "") -> float:
        items = self._items(option)
        return r2(sum(i.tax for i in items) + sum(i.extended for i in items) * self.tax_pct / 100)

    def scope_total(self, option: str = "") -> float:
        return r2(self.scope_line_total(option) + self.scope_tax(option) + self.scope_op(option))

    @property
    def line_item_total(self) -> float:
        return self.scope_line_total()

    @property
    def sales_tax(self) -> float:
        return self.scope_tax()

    @property
    def overhead(self) -> float:
        op = self.scope_op()
        return r2(op * self.overhead_pct / self.op_pct) if self.op_pct else 0.0

    @property
    def profit(self) -> float:
        return r2(self.scope_op() - self.overhead)

    @property
    def grand_total(self) -> float:
        """Base scope total including tax and O&P."""
        return self.scope_total()

    @property
    def total_with_options(self) -> float:
        return r2(self.grand_total + sum(self.scope_total(o) for o in self.options))
