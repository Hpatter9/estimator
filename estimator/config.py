"""Your company details, used on every exported estimate. Edit data/company.json."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

CONFIG_PATH = Path("data/company.json")


class Company(BaseModel):
    name: str = "Your Company Name"
    address: str = ""
    phone: str = ""
    email: str = ""
    license: str = ""
    logo_path: str = ""  # PNG/JPG used on the company template
    estimator: str = ""
    terms: str = ("This estimate is valid for 30 days. Hidden damage discovered during work may require a "
                  "supplement. Pricing based on current material and labor costs.")


def load_company(path: Path = CONFIG_PATH) -> Company:
    if path.exists():
        return Company.model_validate_json(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    company = Company()
    path.write_text(json.dumps(company.model_dump(), indent=2))
    return company
