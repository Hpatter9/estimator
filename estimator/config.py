"""Company details and boilerplate used on exported estimates.

Defaults (your exclusions, waivers, agreement terms, billing schedule) live in
estimator/company_defaults.json. Per-computer overrides go in data/company.json - any field
you put there replaces the default.
"""
from __future__ import annotations

import json
from pathlib import Path

from typing import Optional

from pydantic import BaseModel, Field

DEFAULTS_PATH = Path(__file__).resolve().parent / "company_defaults.json"
CONFIG_PATH = Path("data/company.json")
DEFAULT_LOGO = Path(__file__).resolve().parent / "templates" / "assets" / "logo.png"


class Lead(BaseModel):
    lead: str
    text: str


class WaiverGroup(BaseModel):
    heading: str
    items: list[str]


class Term(BaseModel):
    text: str
    sub: list[str] = Field(default_factory=list)


class Payment(BaseModel):
    label: str  # "Deposit due at signing"
    short: str  # "Deposit at signing" (table column)
    pct: float


class Company(BaseModel):
    name: str = "Your Company Name"
    legal_name: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    estimator: str = ""
    logo_path: str = ""  # PNG with transparent background; defaults to templates/assets/logo.png
    overhead_pct: float = 10.0
    profit_pct: float = 10.0
    # markup for customer Estimates / Agreements; None = use the median of your past jobs (see markup.py)
    markup_pct: Optional[float] = None
    billing: list[Payment] = Field(default_factory=lambda: [
        Payment(label="Deposit due at signing", short="Deposit at signing", pct=50),
        Payment(label="Final invoice on completion", short="Final on completion", pct=50)])
    amounts_note: str = "All amounts include overhead and profit."
    license_line: str = ""
    exclusions: list[Lead] = Field(default_factory=list)
    selection_acknowledgments: list[Lead] = Field(default_factory=list)
    waivers: list[WaiverGroup] = Field(default_factory=list)
    agreement_terms_intro: str = ""
    agreement_terms: list[Term] = Field(default_factory=list)
    agreement_terms_footer: str = ""
    approval_text: str = ""

    @property
    def logo(self) -> Path | None:
        p = Path(self.logo_path) if self.logo_path else DEFAULT_LOGO
        return p if p.exists() else None


def load_company(path: Path = CONFIG_PATH) -> Company:
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8")) if DEFAULTS_PATH.exists() else {}
    if path.exists():
        data.update(json.loads(path.read_text(encoding="utf-8")))
    return Company.model_validate(data)


def save_company(company: Company, path: Path = CONFIG_PATH) -> None:
    """Save only the fields that differ from the defaults."""
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8")) if DEFAULTS_PATH.exists() else {}
    current = json.loads(company.model_dump_json())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in current.items() if defaults.get(k) != v}, indent=2), encoding="utf-8")
