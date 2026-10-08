"""Web app:  streamlit run app.py

1. Library     - upload your past estimates
2. New estimate - notes + DocuSketch files + photos -> draft
3. Review       - edit line items, quantities and prices
4. Export       - download as Xactimate-style PDF, your template, Excel, CSV
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from estimator.config import CONFIG_PATH, Company, load_company
from estimator.export import FORMATS, export
from estimator.library import Library
from estimator.models import Estimate, LineItem, Section

st.set_page_config(page_title="Estimator", layout="wide")
lib = Library()
company = load_company()
UPLOADS = Path(tempfile.gettempdir()) / "estimator_uploads"
UPLOADS.mkdir(exist_ok=True)


def save_upload(f) -> Path:
    p = UPLOADS / f.name
    p.write_bytes(f.getbuffer())
    return p


tab_lib, tab_new, tab_review, tab_export, tab_settings = st.tabs(
    ["1. Past estimates", "2. New estimate", "3. Review & edit", "4. Export", "Settings"])

with tab_lib:
    st.subheader(f"Library: {lib.count()} past estimates")
    files = st.file_uploader("Add past estimates (Xactimate PDFs, your PDFs, CSV/XLSX, JSON)",
                             accept_multiple_files=True, type=["pdf", "csv", "xlsx", "json"])
    use_ai = st.checkbox("Read PDFs with Claude (recommended; works on any layout)", value=True)
    if files and st.button("Import"):
        from estimator.ingest import load_past_estimate
        for f in files:
            with st.spinner(f"Reading {f.name}..."):
                try:
                    est = load_past_estimate(save_upload(f), use_ai=use_ai)
                    lib.add(est)
                    st.success(f"{f.name}: {sum(len(s.items) for s in est.sections)} line items")
                except Exception as e:
                    st.error(f"{f.name}: {e}")
    rows = lib.list()
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True)
        with st.expander("Price book"):
            st.dataframe([e.__dict__ for e in lib.price_book()], use_container_width=True, hide_index=True)

with tab_new:
    c1, c2, c3 = st.columns(3)
    customer = c1.text_input("Customer")
    address = c2.text_input("Property address")
    claim = c3.text_input("Claim #")
    notes = st.text_area("Job notes", height=200,
                         placeholder="Cat 2 water loss from dishwasher supply line. Kitchen + hallway. 2ft flood cut...")
    sketch = st.file_uploader("DocuSketch files (PDF report, CSV/XLSX, ESX)", accept_multiple_files=True,
                              type=["pdf", "csv", "xlsx", "esx", "zip", "json"])
    photos = st.file_uploader("Photos (optional)", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"])
    attach = st.file_uploader("Other documents (optional PDFs: scope sheets, adjuster notes)",
                              accept_multiple_files=True, type=["pdf"])
    c1, c2, c3 = st.columns(3)
    overhead = c1.number_input("Overhead %", value=10.0)
    profit = c2.number_input("Profit %", value=10.0)
    tax = c3.number_input("Sales tax %", value=0.0)
    if st.button("Draft estimate", type="primary", disabled=not notes.strip()):
        from estimator.generate import generate_estimate
        from estimator.ingest.docusketch import load_rooms
        try:
            with st.spinner("Reading DocuSketch files..."):
                rooms = [r for f in sketch or [] for r in load_rooms(save_upload(f))]
            st.write(f"Found {len(rooms)} rooms.")
            with st.spinner("Writing the estimate from your past jobs..."):
                est, questions = generate_estimate(
                    lib, notes, rooms, photos=[save_upload(f) for f in photos or []],
                    extra_files=[save_upload(f) for f in attach or []],
                    customer=customer, address=address, claim_number=claim,
                    overhead_pct=overhead, profit_pct=profit, tax_pct=tax)
            st.session_state["estimate"] = est.model_dump(mode="json")
            st.session_state["questions"] = questions
            st.success(f"Draft ready: ${est.grand_total:,.2f}. Go to Review & edit.")
        except Exception as e:
            st.error(str(e))

with tab_review:
    if "estimate" not in st.session_state:
        st.info("Draft an estimate first.")
    else:
        est = Estimate.model_validate(st.session_state["estimate"])
        for q in st.session_state.get("questions", []):
            st.warning(q)
        est.title = st.text_input("Title", est.title)
        est.summary = st.text_area("Summary", est.summary)
        rows = [{"room": s.name, **i.model_dump()} for s, i in est.all_items()]
        st.caption("Rows with price_source = ai weren't in your price history - check those prices.")
        edited = st.data_editor(rows, num_rows="dynamic", use_container_width=True, key="items")
        if st.button("Save edits"):
            sections: dict[str, Section] = {}
            rooms = {s.name: s.room for s in est.sections}
            for r in edited:
                if not r.get("description"):
                    continue
                name = r.pop("room") or "General"
                sections.setdefault(name, Section(name=name, room=rooms.get(name))).items.append(
                    LineItem.model_validate({k: v for k, v in r.items() if v is not None}))
            est.sections = list(sections.values())
            st.session_state["estimate"] = est.model_dump(mode="json")
            st.success(f"Saved. Total ${est.grand_total:,.2f}")
        if st.button("Add this estimate to my library"):
            lib.add(est)
            st.success("Added - future estimates will learn from it.")

with tab_export:
    if "estimate" not in st.session_state:
        st.info("Draft an estimate first.")
    else:
        est = Estimate.model_validate(st.session_state["estimate"])
        fmts = st.multiselect("Formats", list(FORMATS), default=["xactimate", "company"],
                              format_func=lambda k: FORMATS[k])
        if st.button("Create files"):
            out = Path(tempfile.mkdtemp())
            for fmt in fmts:
                for pth in export(est, fmt, out, company):
                    st.download_button(f"Download {pth.name}", pth.read_bytes(), file_name=pth.name, key=str(pth))

with tab_settings:
    st.caption(f"Saved to {CONFIG_PATH}")
    data = company.model_dump()
    new = {k: (st.text_area(k, v) if k == "terms" else st.text_input(k, v)) for k, v in data.items()}
    if st.button("Save settings"):
        CONFIG_PATH.write_text(Company.model_validate(new).model_dump_json(indent=2))
        st.success("Saved.")
