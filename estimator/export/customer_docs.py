"""Your customer-facing documents:

  * Reconstruction Estimate  - trades with O&P-inclusive totals, plain-English bullets, exclusions,
                               billing schedule (and optional add-on scopes, if any)
  * Reconstruction Agreement - the same scope plus material selections, waivers, the work
                               authorization terms and a signature block

Templates: estimator/templates/reconstruction_estimate.html.j2 / reconstruction_agreement.html.j2.
Boilerplate (exclusions, waivers, terms, billing %): estimator/company_defaults.json.
"""
from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import Company
from ..models import Estimate, LineItem, r2
from ..trades import DEFAULT_NOTES, fill_missing_trades, trade_sort_key
from .pdf import html_to_pdf

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


@dataclass
class TradeBlock:
    name: str
    total: float
    bullets: list[str]
    note: str = ""


@dataclass
class ScopeBlock:
    option: str  # "" = base scope
    title: str
    total: float
    areas: str = ""
    description: str = ""
    trades: list[TradeBlock] = field(default_factory=list)


@dataclass
class BillingRow:
    label: str
    total: float
    payments: list[float]
    strong: bool = True


def payments(total: float, pcts: list[float]) -> list[float]:
    """Split a total by percentages, rounding half-up; the last payment takes the remainder."""
    out = [float(Decimal(str(total * p / 100)).quantize(Decimal("0.01"), ROUND_HALF_UP)) for p in pcts[:-1]]
    return out + [r2(total - sum(out))]


def _bullet(item: LineItem) -> str:
    return item.customer_text or item.description


def build_scopes(est: Estimate) -> list[ScopeBlock]:
    fill_missing_trades(est)
    texts = {(t.option, t.trade): t for t in est.trade_text}
    scope_texts = {s.option: s for s in est.scope_text}
    blocks = []
    for option in ["", *est.options]:
        by_trade: dict[str, list[LineItem]] = {}
        for _, item in est.all_items(option):
            by_trade.setdefault(item.trade, []).append(item)
        trades = []
        for trade in sorted(by_trade, key=trade_sort_key):
            items = by_trade[trade]
            total = r2(sum(i.total_with_op(est.op_pct) for i in items) * (1 + est.markup_pct / 100))
            text = texts.get((option, trade))
            if text and text.bullets:
                bullets, note = text.bullets, text.note
            else:
                bullets = list(dict.fromkeys(_bullet(i) for i in items))
                note = DEFAULT_NOTES.get(trade.split(" — ")[0], "")
            trades.append(TradeBlock(trade, total, bullets, note))
        st = scope_texts.get(option)
        areas = st.areas if st and st.areas else ", ".join(
            dict.fromkeys(s.name for s in est.sections if s.option == option and s.room))
        title = "Base Scope" if not option else f"Optional — {option}"
        blocks.append(ScopeBlock(option, title, r2(sum(t.total for t in trades)), areas,
                                 st.description if st else "", trades))
    return blocks


def billing_rows(scopes: list[ScopeBlock], company: Company, doc: str) -> list[BillingRow]:
    pcts = [p.pct for p in company.billing]
    base_label = "Total Job Price" if doc == "estimate" else "Total Agreement Amount"
    base, options = scopes[0], scopes[1:]
    if not options:
        return [BillingRow(base_label, base.total, payments(base.total, pcts))]
    rows = [BillingRow(f"{base_label} (Base Scope)", base.total, payments(base.total, pcts))]
    for o in options:
        rows.append(BillingRow(f"Optional: {o.option}, if accepted", o.total, payments(o.total, pcts), strong=False))
    combined = r2(sum(s.total for s in scopes))
    names = " and ".join(o.option for o in options)
    rows.append(BillingRow(f"{base_label} with Optional {names}", combined, payments(combined, pcts)))
    return rows


def _data_uri(path: str | Path | None) -> str:
    if not path or not Path(path).exists():
        return ""
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def render(est: Estimate, company: Company, doc: str = "estimate") -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["money"] = lambda v: f"${v:,.2f}"
    env.filters["mdy"] = lambda d: f"{d.month}/{d.day}/{d.year}"
    scopes = build_scopes(est)
    template = "reconstruction_estimate.html.j2" if doc == "estimate" else "reconstruction_agreement.html.j2"
    word = "estimate" if doc == "estimate" else "agreement"
    return env.get_template(template).render(
        est=est, company=company, scopes=scopes, base=scopes[0], has_options=len(scopes) > 1,
        billing=billing_rows(scopes, company, doc), logo=_data_uri(company.logo),
        total_with_options=r2(sum(s.total for s in scopes)),
        exclusions=[(e.lead, e.text.replace("{doc}", word)) for e in company.exclusions],
        selections=[(s, _data_uri(s.image_path)) for s in est.selections],
        estimator=company.estimator,
    )


def write(est: Estimate, path: Path, company: Company, doc: str = "estimate") -> list[Path]:
    """Writes <path>.html and, when a Chrome/Edge/Chromium browser is installed, <path>.pdf."""
    html_path = path.with_suffix(".html")
    html_path.write_text(render(est, company, doc), encoding="utf-8")
    pdf = html_to_pdf(html_path)
    return [pdf, html_path] if pdf else [html_path]
