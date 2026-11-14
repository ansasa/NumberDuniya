"""Admin-only, read-only local OCR review for NumberDuniya.

No database mutations, Gemini calls, cache writes, or publication actions.
This is a separate review workflow until the existing verification schema is mapped.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import streamlit as st
from services.lottery_upload_service import download_lottery_file
from services.local_ocr_service import extract_local_text
from services.lottery_local_parser_service import parse_prize_numbers
from services.lottery_validation_service import validate_lottery_result
from services.lottery_verification_service import validate_draw_metadata
from components.lottery_verification import show_lottery_verification

PROFILE = "nagaland_magic_sunday_8pm"
PRIZES = (("first_prize", "First Prize", 1, 5),
          ("second_prize", "Second Prize", 10, 5),
          ("third_prize", "Third Prize", 10, 4),
          ("fourth_prize", "Fourth Prize", 10, 4),
          ("fifth_prize", "Fifth Prize", 100, 4))


def _draw_label(record):
    draw = record.get("lottery_draws") or {}
    return (f"{draw.get('lottery_name') or 'Unknown'} | "
            f"{draw.get('result_date') or 'No date'} | "
            f"{draw.get('draw_time') or 'No time'} | "
            f"{record.get('file_name') or 'Unnamed'}")


def _normalize_time(value):
    try:
        return datetime.strptime(str(value)[:8], "%H:%M:%S").strftime("%I:%M %p")
    except (ValueError, TypeError):
        return str(value or "")


def _validate_tokens(name, text, expected, digits):
    tokens = text.split()
    errors = []
    if len(tokens) != expected:
        errors.append(f"{name}: {len(tokens)}/{expected} entries.")
    for index, token in enumerate(tokens, 1):
        if digits == 5 and expected == 1:
            valid = bool(re.fullmatch(r"\d{1,3}[A-Za-z]\s+\d{5}", text.strip()))
            if not valid:
                errors.append("First Prize must look like 34J 12030 (series and 5 digits).")
            return [text.strip()] if valid else [], errors
        if not re.fullmatch(rf"\d{{{digits}}}", token):
            errors.append(f"{name}: entry {index} has invalid format: {token!r}.")
    return tokens, errors


def show_local_ocr_review(admin_client, uploaded_results):
    st.subheader("Local OCR — Prize-wise Admin Review")
    st.caption("Offline Tesseract OCR; no Gemini calls. Nothing is saved or published automatically.")
    pending = [r for r in (uploaded_results or [])
               if (r.get("lottery_draws") or {}).get("status") == "pending"
               and r.get("file_type") in ("application/pdf", "image/jpeg", "image/png")]
    if not pending:
        st.info("No pending supported uploads available.")
        return
    options = {str(r["upload_id"]): r for r in pending}
    selected_id = st.selectbox("Pending result", list(options),
                               format_func=lambda key: _draw_label(options[key]),
                               key="nd_local_selected_upload")
    record = options[selected_id]
    draw = record.get("lottery_draws") or {}
    st.write("**Lottery:**", draw.get("lottery_name") or "N/A")
    st.write("**Date (uploaded metadata):**", draw.get("result_date") or "N/A")
    st.write("**Draw time (uploaded metadata):**", _normalize_time(draw.get("draw_time")))
    st.warning("This crop profile supports only Nagaland Magic Sunday 8 PM. Do not use it for other layouts.")
    if st.button("Extract locally for review", key=f"nd_local_extract_{selected_id}"):
        if "nagaland" not in str(draw.get("lottery_name", "")).lower() or _normalize_time(draw.get("draw_time")) != "08:00 PM":
            st.error("Selected draw is not a Nagaland 8 PM draw. Extraction was not started.")
        else:
            try:
                with st.spinner("Running local OCR on selected upload..."):
                    source = download_lottery_file(admin_client, record["storage_path"])
                    ocr = extract_local_text(source, record["file_type"], layout_profile=PROFILE)
                    review = parse_prize_numbers(ocr)
                st.session_state["nd_local_review"] = {"upload_id": selected_id, "review": review}
                for key, _, _, _ in PRIZES:
                    st.session_state[f"nd_local_{selected_id}_{key}"] = "\n".join(review["prizes"][key]["numbers"])
                st.success("Local OCR complete. Check every entry against the original PDF.")
            except Exception as exc:
                st.error(f"Local OCR failed: {exc}")
    state = st.session_state.get("nd_local_review")
    if not state or state.get("upload_id") != selected_id:
        return
    review = state["review"]
    st.caption("OCR metadata is only a suggestion. Uploaded draw date/time remain authoritative until manually checked.")
    if review.get("warnings"):
        for warning in review["warnings"]:
            st.warning(warning)
    st.download_button("Download original file for comparison",
                       data=download_lottery_file(admin_client, record["storage_path"]),
                       file_name=record.get("file_name") or "original.pdf",
                       mime=record["file_type"], key=f"nd_local_original_{selected_id}")
    st.subheader("Edit extracted winning numbers")
    st.caption("Enter one number per line. First Prize: one line containing series and number, e.g. 34J 12030.")
    with st.form(f"nd_local_form_{selected_id}"):
        for key, title, expected, _ in PRIZES:
            st.text_area(f"{title} — expected {expected}",
                         key=f"nd_local_{selected_id}_{key}",
                         height=85 if expected < 100 else 260)
        checked = st.checkbox("I have checked every number against the original result")
        submitted = st.form_submit_button("Validate reviewed numbers")
    if not submitted:
        _show_transfer_if_ready(selected_id, record)
        return
    cleaned, errors = {}, []
    for key, title, expected, digits in PRIZES:
        raw = st.session_state[f"nd_local_{selected_id}_{key}"]
        if key == "first_prize":
            value = raw.strip()
            if not re.fullmatch(r"\d{1,3}[A-Za-z]\s+\d{5}", value):
                errors.append("First Prize must look like 34J 12030.")
            cleaned[key] = [re.sub(r"\s+", " ", value)] if value else []
        else:
            tokens = raw.split()
            cleaned[key] = tokens
            if len(tokens) != expected:
                errors.append(f"{title}: {len(tokens)}/{expected} entries.")
            for i, token in enumerate(tokens, 1):
                if not re.fullmatch(rf"\d{{{digits}}}", token):
                    errors.append(f"{title}: invalid number #{i}: {token!r}")
    if not checked:
        errors.append("Manual verification confirmation is required.")
    if errors:
        st.session_state.pop("nd_local_verified_snapshot", None)
        for error in errors:
            st.error(error)
        return
    export = {
        "status": "manually_reviewed_local_draft",
        "upload_id": selected_id,
        "draw_id": str(record.get("draw_id") or draw.get("draw_id") or ""),
        "lottery_name": draw.get("lottery_name"),
        "result_date": draw.get("result_date"),
        "draw_time": draw.get("draw_time"),
        "layout_profile": PROFILE,
        "prizes": cleaned,
        "ocr_warnings": review.get("warnings", []),
        "publish_authorized": False,
    }
    # Convert the local parser dictionary into the existing RPC prize schema.
    category_map = (
        ("first_prize", "1st Prize"),
        ("second_prize", "2nd Prize"),
        ("third_prize", "3rd Prize"),
        ("fourth_prize", "4th Prize"),
        ("fifth_prize", "5th Prize"),
    )
    draft = {
        "lottery_name": str(draw.get("lottery_name") or "").strip(),
        "result_date": str(draw.get("result_date") or ""),
        "draw_time": str(draw.get("draw_time") or ""),
        "prizes": [
            {"category_name": category, "prize_amount": None,
             "winning_numbers": cleaned[key]}
            for key, category in category_map
        ],
    }
    # Require trusted upload metadata and complete structural validation.
    draw_id = str(record.get("draw_id") or draw.get("draw_id") or "")
    if not draw_id:
        st.error("Missing draw_id. Cannot transfer to verification.")
        return
    errors = validate_lottery_result(draft) + validate_draw_metadata(draft, draw)
    if errors:
        for error in errors:
            st.error(error)
        return
    st.session_state["nd_local_verified_snapshot"] = {
        "upload_id": selected_id, "draw_id": draw_id, "draft": draft,
        "widgets": {key: st.session_state[f"nd_local_{selected_id}_{key}"]
                    for key, _, _, _ in PRIZES},
    }
    st.success("All 131 entries pass format/count checks and manual review was confirmed. Not saved to database.")
    st.download_button("Download reviewed draft JSON", json.dumps(export, indent=2),
                       file_name=f"numberduniya_review_{selected_id}.json", mime="application/json",
                       key=f"nd_local_export_{selected_id}")
    _show_transfer_if_ready(selected_id, record)


def _show_transfer_if_ready(selected_id, record):
    snapshot = st.session_state.get("nd_local_verified_snapshot")
    if not snapshot or snapshot.get("upload_id") != selected_id:
        return

    # Re-check all editable widgets; changes invalidate the confirmed snapshot.
    for key, _, _, _ in PRIZES:
        if st.session_state.get(f"nd_local_{selected_id}_{key}") != snapshot["widgets"][key]:
            st.warning("Reviewed numbers changed. Validate and confirm again before transfer.")
            return

    draft = snapshot["draft"]
    draw_id = snapshot["draw_id"]
    st.subheader("Transfer to Secure Verification")
    st.info("This transfers the manually reviewed draft to the existing admin verification workflow. No database write occurs until you explicitly approve verification.")
    if st.button("Use reviewed Local OCR data for verification",
                 key=f"nd_transfer_{selected_id}"):
        st.session_state["extracted_lottery_data"] = draft
        st.session_state["extraction_upload_id"] = selected_id
        st.session_state["extraction_validation_errors"] = []
        st.session_state["extraction_from_cache"] = False
        for k in ("reviewed_lottery_data", "reviewed_draw_id", "reviewed_upload_id",
                  "reviewed_expected_counts", "review_reference"):
            st.session_state.pop(k, None)
        st.session_state["nd_local_transfer_upload"] = selected_id
        st.rerun()

    if st.session_state.get("nd_local_transfer_upload") == selected_id:
        st.divider()
        show_lottery_verification(
            extracted_data=draft,
            draw_id=draw_id,
            upload_id=selected_id,
        )
