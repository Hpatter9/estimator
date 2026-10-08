"""Web app:  streamlit run app.py

1. Library      - upload past Xactimate estimates and your customer Estimates / Agreements
2. New estimate - notes + DocuSketch ESX + photos -> draft
   Convert      - or start from an existing Xactimate PDF
3. Review       - edit line items, trades, quantities and prices
4. Export       - Reconstruction Estimate, Reconstruction Agreement, Xactimate-style PDF, Excel
(For hundreds of files, use the command line: python -m estimator import "C:/Estimates")
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from estimator.config import CONFIG_PATH, load_company, save_company
from estimator.export import FORMATS, export
from estimator.library import Library
from estimator.models import Estimate, LineItem, MaterialSelection, Room, Section, SelectionField, TradeText

st.set_page_config(page_title="Estimator", layout="wide")
lib = Library()
company = load_company()
UPLOADS = Path(tempfile.gettempdir()) / "estimator_uploads"
UPLOADS.mkdir(exist_ok=True)


def save_upload(f) -> Path:
    p = UPLOADS / f.name
    p.write_bytes(f.getbuffer())
    return p


tab_lib, tab_new, tab_conv, tab_review, tab_export, tab_settings = st.tabs(
    ["1. Library", "2. New estimate", "2b. Convert Xactimate", "3. Review & edit", "4. Export", "Settings"])

with tab_lib:
    st.subheader(f"Library: {lib.count()} estimates, {len(lib.list_style_examples())} customer documents")
    files = st.file_uploader("Add Xactimate PDFs (they teach line items and prices) and your Reconstruction "
                             "Estimates / Agreements (they teach your wording). Already-imported files are skipped.",
                             accept_multiple_files=True, type=["pdf", "csv", "xlsx", "json"])
    use_ai = st.checkbox("Use Claude for PDFs that aren't Xactimate", value=True)
    if files and st.button("Import"):
        from estimator.ingest import import_into_library
        log = st.empty()
        lines: list[str] = []

        def show(msg):
            lines.append(msg)
            log.code("\n".join(lines[-30:]))

        counts = import_into_library(lib, [save_upload(f) for f in files], use_ai=use_ai, progress=show)
        st.success(f"{counts['estimate']} estimates, {counts['style']} customer documents, "
                   f"{counts['duplicate']} already imported, {counts['error']} errors")
    rows = lib.list()
    if rows:
        st.dataframe([dict(r) for r in rows], width="stretch", hide_index=True)
        with st.expander("Price book"):
            st.dataframe([e.__dict__ for e in lib.price_book()], width="stretch", hide_index=True)
        with st.expander("Customer documents (style examples)"):
            st.dataframe([dict(r) for r in lib.list_style_examples()], width="stretch", hide_index=True)

with tab_new:
    c1, c2, c3 = st.columns(3)
    customer = c1.text_input("Customer")
    address = c2.text_input("Property address")
    claim = c3.text_input("Claim #")
    notes = st.text_area("Job notes", height=200,
                         placeholder="Cat 2 water loss from dishwasher supply line. Kitchen + hallway. 2ft flood cut...")
    sketch = st.file_uploader("DocuSketch files (the .ESX from the job folder; PDF or CSV also work)",
                              accept_multiple_files=True,
                              type=["pdf", "csv", "xlsx", "esx", "zip", "json"])
    if sketch and st.button("Read rooms"):
        from estimator.ingest.docusketch import load_rooms
        try:
            with st.spinner("Reading DocuSketch files..."):
                st.session_state["rooms"] = [r.model_dump() for f in sketch for r in load_rooms(save_upload(f))]
        except Exception as e:
            st.error(str(e))
    if st.session_state.get("rooms"):
        st.caption("Rooms from DocuSketch. DocuSketch exports every room at 8' - fix ceiling heights here and wall SF "
                   "is recalculated. Untick rooms that aren't part of the job.")
        room_rows = [{"include": True, "name": r["name"], "height_ft": r["height_ft"], "floor_sf": r["floor_sf"],
                      "wall_sf": r["wall_sf"], "perimeter_lf": r["perimeter_lf"]} for r in st.session_state["rooms"]]
        edited_rooms = st.data_editor(room_rows, width="stretch", key="room_table",
                                      disabled=["floor_sf", "wall_sf", "perimeter_lf"])
    photos = st.file_uploader("Photos (optional)", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"])
    attach = st.file_uploader("Other documents (optional PDFs: scope sheets, adjuster notes)",
                              accept_multiple_files=True, type=["pdf"])
    c1, c2, c3 = st.columns(3)
    overhead = c1.number_input("Overhead %", value=company.overhead_pct)
    profit = c2.number_input("Profit %", value=company.profit_pct)
    tax = c3.number_input("Sales tax %", value=0.0)
    if st.button("Draft estimate", type="primary", disabled=not notes.strip()):
        from estimator.generate import generate_estimate
        from estimator.markup import default_markup
        rooms = []
        for raw, row in zip(st.session_state.get("rooms", []), edited_rooms if st.session_state.get("rooms") else []):
            if not row["include"]:
                continue
            room = Room.model_validate(raw)
            room.name = row["name"] or room.name
            if row["height_ft"] and row["height_ft"] != raw["height_ft"]:
                room.set_height(float(row["height_ft"]))
            rooms.append(room)
        try:
            with st.spinner("Writing the estimate from your past jobs..."):
                est, questions = generate_estimate(
                    lib, notes, rooms, photos=[save_upload(f) for f in photos or []],
                    extra_files=[save_upload(f) for f in attach or []],
                    customer=customer, address=address, claim_number=claim,
                    overhead_pct=overhead, profit_pct=profit, tax_pct=tax)
            est.markup_pct = default_markup(lib, company)
            st.session_state["estimate"] = est.model_dump(mode="json")
            st.session_state["questions"] = questions
            st.success(f"Draft ready: ${est.grand_total:,.2f}. Go to Review & edit.")
        except Exception as e:
            st.error(str(e))

with tab_conv:
    st.write("Turn an existing Xactimate estimate into your Reconstruction Estimate / Agreement.")
    xpdf = st.file_uploader("Xactimate PDF", type=["pdf"], key="xpdf")
    if xpdf:
        from estimator.ingest.xactimate_pdf import parse_xactimate
        parsed = parse_xactimate(save_upload(xpdf))
        st.write(f"{sum(len(s.items) for s in parsed.estimate.sections)} line items: {parsed.report()}")
        rooms = [s.name for s in parsed.estimate.sections]
        optional = st.multiselect("Rooms to price as optional add-ons", rooms)
        opt_name = st.text_input("Name for the optional add-on", "Optional Repairs") if optional else ""
        if st.button("Write customer scope", type="primary"):
            from estimator.customer import write_customer_scope
            est = parsed.estimate
            for s in est.sections:
                if s.name in optional:
                    s.option = opt_name
            est.estimate_numbers = [est.title]
            from estimator.markup import default_markup
            est.markup_pct = default_markup(lib, company)
            try:
                with st.spinner("Writing the customer scope in your style..."):
                    write_customer_scope(est, lib.style_examples())
                st.session_state["estimate"] = est.model_dump(mode="json")
                st.session_state["questions"] = []
                st.success("Done. Review it in 3, then export in 4.")
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
        est.intro = st.text_area("Intro box (only shown when there are optional add-ons)", est.intro)
        rows = [{"room": s.name, "optional": s.option, **i.model_dump()} for s, i in est.all_items()]
        st.caption("Line items. Rows with price_source = ai weren't in your price history - check those prices. "
                   "'optional' = name of an optional add-on (blank = base scope); 'trade' = section on your "
                   "customer estimate.")
        edited = st.data_editor(rows, num_rows="dynamic", width="stretch", key="items")
        st.caption("Customer bullets per trade (one bullet per line).")
        trade_rows = [{"trade": t.trade, "optional": t.option, "bullets": "\n".join(t.bullets), "note": t.note}
                      for t in est.trade_text]
        edited_trades = st.data_editor(trade_rows, num_rows="dynamic", width="stretch", key="trades")
        if st.button("Save edits"):
            sections: dict[tuple[str, str], Section] = {}
            rooms = {s.name: s.room for s in est.sections}
            for r in edited:
                if not r.get("description"):
                    continue
                name = r.pop("room") or "General"
                option = r.pop("optional") or ""
                sections.setdefault((name, option), Section(name=name, room=rooms.get(name), option=option)).items.append(
                    LineItem.model_validate({k: v for k, v in r.items() if v is not None}))
            est.sections = list(sections.values())
            est.trade_text = [TradeText(trade=t["trade"], option=t.get("optional") or "",
                                        bullets=[b.strip() for b in (t.get("bullets") or "").splitlines() if b.strip()],
                                        note=t.get("note") or "")
                              for t in edited_trades if t.get("trade")]
            st.session_state["estimate"] = est.model_dump(mode="json")
            st.success(f"Saved. Total ${est.grand_total:,.2f}" +
                       "".join(f" | optional {o}: ${est.scope_total(o):,.2f}" for o in est.options))
        with st.expander(f"Material selections for the Agreement ({len(est.selections)}) - optional"):
            st.caption("Leave empty if there are no customer selections; the Agreement then skips that section.")
            viewed_opts = ["Online only (not viewed in person)", "Viewed in person"]
            kept = []
            for i, sel in enumerate(est.selections):
                st.markdown(f"**Selection {i + 1}**")
                c1, c2 = st.columns([3, 1])
                title = c1.text_input("Title", sel.title, key=f"sel_title_{i}",
                                      placeholder="Vinyl Plank Flooring — Bathroom")
                remove = c2.checkbox("Remove", key=f"sel_rm_{i}")
                details = st.text_area("Details, one per line as LABEL: value", key=f"sel_fields_{i}",
                                       value="\n".join(f"{f.label}: {f.value}" for f in sel.fields))
                c1, c2 = st.columns(2)
                viewed = c1.selectbox("Viewed", viewed_opts, key=f"sel_viewed_{i}",
                                      index=viewed_opts.index(sel.viewed) if sel.viewed in viewed_opts else 0)
                caption = c2.text_input("Photo caption", sel.caption, key=f"sel_cap_{i}")
                photo = st.file_uploader("Photo", type=["jpg", "jpeg", "png", "webp"], key=f"sel_img_{i}")
                image_path = sel.image_path
                if photo:
                    folder = Path("data/selections")
                    folder.mkdir(parents=True, exist_ok=True)
                    image_path = str(folder / photo.name)
                    Path(image_path).write_bytes(photo.getbuffer())
                if not remove:
                    fields = [SelectionField(label=l.split(":", 1)[0].strip().upper(), value=l.split(":", 1)[1].strip())
                              for l in details.splitlines() if ":" in l]
                    kept.append(MaterialSelection(title=title, fields=fields, image_path=image_path,
                                                  caption=caption, viewed=viewed))
            c1, c2 = st.columns(2)
            if c1.button("Save selections"):
                est.selections = kept
                st.session_state["estimate"] = est.model_dump(mode="json")
                st.success(f"Saved {len(kept)} selections.")
            if c2.button("Add a selection"):
                est.selections = kept + [MaterialSelection(title="", fields=[
                    SelectionField(label=l, value="") for l in ("BRAND", "PRODUCT", "SKU / COLOR", "SIZE")])]
                st.session_state["estimate"] = est.model_dump(mode="json")
                st.rerun()
        if st.button("Add this estimate to my library"):
            lib.add(est)
            st.success("Added - future estimates will learn from it.")

with tab_export:
    if "estimate" not in st.session_state:
        st.info("Draft an estimate first.")
    else:
        est = Estimate.model_validate(st.session_state["estimate"])
        from estimator.markup import suggested
        hint = suggested(lib)
        est.markup_pct = st.number_input(
            "Markup % on the customer Estimate / Agreement (the Xactimate-style PDF is not marked up)",
            value=float(est.markup_pct), step=0.5,
            help=f"Median of your past jobs: {hint:.1f}%" if hint is not None else None)
        st.session_state["estimate"] = est.model_dump(mode="json")
        fmts = st.multiselect("Formats", list(FORMATS), default=["estimate", "agreement", "xactimate"],
                              format_func=lambda k: FORMATS[k])
        if st.button("Create files"):
            out = Path(tempfile.mkdtemp())
            for fmt in fmts:
                for pth in export(est, fmt, out, company):
                    st.download_button(f"Download {pth.name}", pth.read_bytes(), file_name=pth.name, key=str(pth))

with tab_settings:
    st.caption(f"Changes are saved to {CONFIG_PATH}. Exclusions, waivers and agreement terms live in "
               "estimator/company_defaults.json.")
    simple = {k: v for k, v in company.model_dump().items() if isinstance(v, (str, float, int))}
    new = {k: (st.number_input(k, value=float(v)) if isinstance(v, (float, int)) else st.text_input(k, v))
           for k, v in simple.items()}
    if st.button("Save settings"):
        save_company(company.model_copy(update=new))
        st.success("Saved.")
