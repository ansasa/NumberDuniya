from services.lottery_delete_service import delete_pending_lottery_result
import streamlit as st
from datetime import datetime, date, time

from components.pdf_upload import show_pdf_upload
from components.lottery_verification import show_lottery_verification
from components.numberduniya_local_review import show_local_ocr_review

from services.dashboard_service import (
    get_dashboard_metrics,
    get_uploaded_results,
)
from services.lottery_upload_service import download_lottery_file
from services.gemini_extraction_service import (
    extract_lottery_result,
    validate_extraction_completeness,
)
from services.lottery_extraction_cache_service import (
    get_cached_extraction,
    save_extraction_cache,
)
from services.lottery_validation_service import validate_lottery_result
from services.lottery_count_presets import get_expected_prize_counts
from services.lottery_verification_service import validate_draw_metadata


# ==========================================
# REVIEW STATE HELPERS
# ==========================================

def clear_review_state(upload_id):
    """Clear review widgets while preserving extracted JSON."""
    for key in (
        "reviewed_lottery_data",
        "reviewed_draw_id",
        "reviewed_upload_id",
        "reviewed_expected_counts",
        "review_reference",
    ):
        st.session_state.pop(key, None)

    prefixes = (
        f"review_numbers_{upload_id}_",
        f"expected_count_{upload_id}_",
    )
    confirmation_key = f"verification_confirm_{upload_id}"

    for key in list(st.session_state.keys()):
        if key.startswith(prefixes) or key == confirmation_key:
            st.session_state.pop(key, None)


def validate_extraction_for_draw(
    extracted_data,
    draw_record,
    expected_counts,
):
    """Validate extraction against trusted Supabase draw metadata."""

    def check(label, function):
        try:
            return function() or []
        except (ValueError, TypeError, KeyError) as error:
            return [f"{label}: {error}"]

    structural_errors = check(
        "Structural validation failed",
        lambda: validate_lottery_result(extracted_data),
    )

    metadata_errors = check(
        "Draw metadata validation failed",
        lambda: validate_draw_metadata(
            extracted_data,
            draw_record,
        ),
    )

    completeness_errors = check(
        "Completeness validation failed",
        lambda: validate_extraction_completeness(
            extracted_data,
            expected_counts=expected_counts,
        ),
    )

    return list(dict.fromkeys(
        structural_errors + metadata_errors + completeness_errors
    ))


# ==========================================
# EDIT PENDING LOTTERY METADATA
# SECURE SUPABASE RPC INTEGRATION
# ==========================================

def show_edit_lottery_metadata(admin_client):
    """Edit pending lottery metadata through admin-authorized RPC."""

    st.subheader("✏️ Edit Uploaded Lottery Metadata")

    st.info(
        "Correct metadata using the original lottery result. "
        "Only pending draws are editable."
    )

    try:
        response = (
            admin_client.table("lottery_draws")
            .select(
                "draw_id, state_name, lottery_name, "
                "scheme_name, result_date, draw_time, "
                "draw_number, status"
            )
            .eq("status", "pending")
            .order("result_date", desc=True)
            .execute()
        )
        draws = response.data or []

    except Exception as error:
        st.error(f"Unable to load pending draws: {error}")
        return

    if not draws:
        st.info("No pending lottery results available.")
        return

    options = {
        str(draw["draw_id"]): draw
        for draw in draws
    }

    draw_id = st.selectbox(
        "Select Pending Lottery Draw",
        options=list(options.keys()),
        format_func=lambda key: (
            f"{options[key].get('lottery_name') or 'Unknown'}"
            f" | {options[key].get('result_date') or 'N/A'}"
        ),
        key="metadata_selected_draw",
    )

    selected = options[draw_id]

    try:
        current_date = date.fromisoformat(
            str(selected["result_date"])
        )
        current_time = time.fromisoformat(
            str(selected["draw_time"])
        )
    except (ValueError, TypeError, KeyError):
        st.error("Existing draw date/time is invalid.")
        return

    st.warning(
        "Verify all fields against the original document. "
        "Editing uploaded metadata does not automatically "
        "correct the Gemini-extracted draft."
    )

    with st.form(f"metadata_edit_{draw_id}"):

        state_name = st.text_input(
            "State",
            value=selected.get("state_name") or "",
        )

        lottery_name = st.text_input(
            "Lottery Operator / Name",
            value=selected.get("lottery_name") or "",
        )

        scheme_name = st.text_input(
            "Lottery Scheme",
            value=selected.get("scheme_name") or "",
        )

        result_date = st.date_input(
            "Result Date",
            value=current_date,
            format="DD/MM/YYYY",
        )

        draw_time = st.time_input(
            "Draw Time",
            value=current_time,
            step=60,
        )

        draw_number = st.text_input(
            "Draw Number",
            value=str(selected.get("draw_number") or ""),
        )

        confirmed = st.checkbox(
            "I have verified the metadata against "
            "the original lottery result."
        )

        submitted = st.form_submit_button(
            "💾 Save Metadata Changes",
            use_container_width=True,
        )

    if not submitted:
        return

    if not confirmed:
        st.warning("Please confirm manual verification.")
        return

    if not state_name.strip():
        st.error("State is required.")
        return

    if not lottery_name.strip():
        st.error("Lottery operator/name is required.")
        return

    payload = {
        "state_name": state_name.strip(),
        "lottery_name": lottery_name.strip(),
        "scheme_name": scheme_name.strip(),
        "result_date": result_date.isoformat(),
        "draw_time": draw_time.strftime("%H:%M:%S"),
        "draw_number": draw_number.strip() or None,
    }

    try:
        # ======================================
        # SECURE DATABASE RPC
        # ======================================
        # The RPC checks auth.uid(), admin_users,
        # required metadata, and pending status.
        # Direct table UPDATE is not required.

        with st.spinner("Saving lottery metadata..."):
            admin_client.rpc(
                "update_pending_lottery_metadata",
                {
                    "p_draw_id": draw_id,
                    "p_state_name": payload["state_name"],
                    "p_lottery_name": payload["lottery_name"],
                    "p_scheme_name": payload["scheme_name"],
                    "p_result_date": payload["result_date"],
                    "p_draw_time": payload["draw_time"],
                    "p_draw_number": payload["draw_number"],
                },
            ).execute()

        # ======================================
        # CLEAR STALE SESSION EXTRACTION
        # ======================================
        # Persistent cached drafts remain stored.
        # They must be manually reviewed again.

        for key in (
            "extracted_lottery_data",
            "extraction_upload_id",
            "extraction_validation_errors",
            "extraction_from_cache",
            "reviewed_lottery_data",
            "reviewed_draw_id",
            "reviewed_upload_id",
            "reviewed_expected_counts",
            "review_reference",
        ):
            st.session_state.pop(key, None)

        st.session_state["metadata_update_message"] = (
            "Lottery metadata updated successfully. "
            "Review and correct Gemini extraction separately."
        )

        st.rerun()

    except Exception as error:
        st.error(
            "Unable to save metadata. "
            f"Database response: {error}"
        )


# ==========================================
# CORRECT VERIFIED DRAW STATE
# ADMIN-ONLY, STATE-ONLY SECURE RPC
# ==========================================

def show_correct_verified_state(admin_client):
    """Correct only the state of a verified draw using an admin-authorized RPC."""

    st.subheader("🛠️ Correct Verified State")
    st.info(
        "Correct the State field on an already verified draw. "
        "Lottery scheme is optional. This action does not modify "
        "winning numbers, verification status, or publication status."
    )

    try:
        response = (
            admin_client.table("lottery_draws")
            .select(
                "draw_id, state_name, lottery_name, scheme_name, "
                "result_date, draw_time, status"
            )
            .eq("status", "verified")
            .order("result_date", desc=True)
            .execute()
        )
        verified_draws = response.data or []
    except Exception as error:
        st.error(f"Unable to load verified draws: {error}")
        return

    if not verified_draws:
        st.info("No verified draws are available for State correction.")
        return

    draw_options = {
        str(draw["draw_id"]): draw for draw in verified_draws
    }
    selected_draw_id = st.selectbox(
        "Select verified lottery draw",
        options=list(draw_options.keys()),
        format_func=lambda draw_id: (
            f"{draw_options[draw_id].get('lottery_name') or 'Unknown Lottery'} | "
            f"{draw_options[draw_id].get('result_date') or 'N/A'} | "
            f"{draw_options[draw_id].get('draw_time') or 'N/A'}"
        ),
        key="verified_state_selected_draw",
    )
    selected = draw_options[selected_draw_id]

    st.write("**Lottery Operator:**", selected.get("lottery_name") or "N/A")
    st.write("**Current State:**", selected.get("state_name") or "N/A")
    st.write("**Lottery Scheme (optional):**", selected.get("scheme_name") or "N/A")
    st.write("**Current Status:**", selected.get("status") or "N/A")

    with st.form(f"correct_verified_state_{selected_draw_id}"):
        new_state = st.text_input(
            "Correct State",
            value=selected.get("state_name") or "",
        )
        confirmed = st.checkbox(
            "I checked the State against the original lottery result "
            "and authorize this State-only correction."
        )
        submitted = st.form_submit_button(
            "💾 Save Verified State Correction",
            use_container_width=True,
        )

    if not submitted:
        return

    if not confirmed:
        st.warning("Please confirm that you checked the original result.")
        return

    new_state = new_state.strip()
    if not new_state:
        st.error("State is required.")
        return

    if new_state == (selected.get("state_name") or "").strip():
        st.info("State is already set to this value. No update is necessary.")
        return

    try:
        with st.spinner("Correcting verified State securely..."):
            admin_client.rpc(
                "correct_verified_lottery_state",
                {
                    "p_draw_id": selected_draw_id,
                    "p_state_name": new_state,
                },
            ).execute()

        st.session_state["verified_state_correction_message"] = (
            "Verified draw State corrected successfully. "
            "Winning numbers and verification status were not modified."
        )
        st.rerun()
    except Exception as error:
        st.error(f"State correction failed. Database response: {error}")


# ==========================================
# APPROVE AND PUBLISH
# ==========================================

def show_publish_results(admin_client):
    """
    Publish an already verified lottery draw.

    Requires:
    - Authenticated admin
    - Verified draw
    - Human confirmation
    - Secure PostgreSQL RPC
    """

    st.subheader("🚀 Approve & Publish")

    st.info(
        "Only verified lottery results are eligible for publication. "
        "Publishing makes the result eligible for public display."
    )

    try:
        response = (
            admin_client.table("lottery_draws")
            .select(
                "draw_id, state_name, lottery_name, scheme_name, "
                "result_date, draw_time, draw_number, status"
            )
            .eq("status", "verified")
            .order("result_date", desc=True)
            .execute()
        )

        verified_draws = response.data or []

    except Exception as error:
        st.error(f"Unable to load verified draws: {error}")
        return

    if not verified_draws:
        st.success(
            "No verified lottery results are currently "
            "waiting for publication."
        )
        return

    st.write(
        f"**Verified results awaiting publication: "
        f"{len(verified_draws)}**"
    )

    draw_options = {
        str(draw["draw_id"]): draw
        for draw in verified_draws
    }

    selected_draw_id = st.selectbox(
        "Select verified lottery result",
        options=list(draw_options.keys()),
        format_func=lambda draw_id: (
            f"{draw_options[draw_id].get('state_name') or 'Unknown State'} | "
            f"{draw_options[draw_id].get('scheme_name') or draw_options[draw_id].get('lottery_name') or 'Unknown Lottery'} | "
            f"{draw_options[draw_id]['result_date']} | "
            f"{draw_options[draw_id]['draw_time']}"
        ),
        key="publish_selected_draw",
    )

    selected_draw = draw_options[selected_draw_id]

    st.divider()
    st.subheader("📋 Publication Details")

    st.write(
        "**State:**",
        selected_draw.get("state_name") or "N/A",
    )
    st.write(
        "**Lottery Operator:**",
        selected_draw.get("lottery_name") or "N/A",
    )
    st.write(
        "**Lottery Scheme:**",
        selected_draw.get("scheme_name") or "N/A",
    )
    st.write(
        "**Result Date:**",
        selected_draw.get("result_date"),
    )
    st.write(
        "**Draw Time:**",
        selected_draw.get("draw_time"),
    )
    st.write(
        "**Draw Number:**",
        selected_draw.get("draw_number") or "N/A",
    )
    st.write(
        "**Current Status:**",
        selected_draw.get("status"),
    )

    st.warning(
        "Publishing is a final administrative action. "
        "Verify the original lottery result and all "
        "winning numbers before proceeding."
    )

    confirmation_key = (
        f"publish_confirmation_{selected_draw_id}"
    )

    confirmed = st.checkbox(
        "I confirm that this lottery result has been "
        "manually verified and is approved for publication.",
        key=confirmation_key,
    )

    if st.button(
        "🚀 Publish Verified Result",
        type="primary",
        disabled=not confirmed,
        key=f"publish_draw_{selected_draw_id}",
    ):
        try:
            latest_response = (
                admin_client.table("lottery_draws")
                .select("draw_id, status")
                .eq("draw_id", selected_draw_id)
                .limit(1)
                .execute()
            )

            if not latest_response.data:
                st.error(
                    "Selected lottery draw no longer exists."
                )
                return

            latest_status = latest_response.data[0].get(
                "status"
            )

            if latest_status != "verified":
                st.error(
                    "This lottery result is no longer "
                    "eligible for publication."
                )
                return

            with st.spinner("Publishing lottery result..."):
                admin_client.rpc(
                    "publish_verified_lottery_result",
                    {
                        "p_draw_id": selected_draw_id,
                    },
                ).execute()

            st.session_state[
                "publication_success_message"
            ] = (
                "Lottery result published successfully. "
                "Publication audit recorded."
            )

            st.session_state.pop(
                confirmation_key,
                None,
            )

            st.rerun()

        except Exception as error:
            st.error(
                "Publication failed. The result was not "
                "confirmed as published. "
                f"Database response: {error}"
            )


# ==========================================
# MAIN ADMIN DASHBOARD
# ==========================================

def show_delete_pending_result(admin_client):
    """
    Permanently delete a pending lottery result or
    resume cleanup for a draw already in 'deleting' status.

    Database authorization and status transitions
    are enforced by protected Supabase RPCs.
    """

    st.subheader("🗑️ Delete Pending Lottery Result")

    st.warning(
        "This permanently removes the selected draw, "
        "its linked database records and uploaded files. "
        "Verified and published results cannot be deleted."
    )

    # ==========================================
    # LOAD PENDING AND DELETING DRAWS
    # ==========================================

    try:
        response = (
            admin_client.table("lottery_draws")
            .select(
                "draw_id, state_name, lottery_name, "
                "scheme_name, result_date, draw_time, status"
            )
            .in_("status", ["pending", "deleting"])
            .order("result_date", desc=True)
            .execute()
        )

        eligible_draws = response.data or []

    except Exception as error:
        st.error(
            f"Unable to load eligible results: {error}"
        )
        return

    if not eligible_draws:
        st.info(
            "No pending results or incomplete deletions "
            "are available."
        )
        return

    options = {
        str(draw["draw_id"]): draw
        for draw in eligible_draws
    }

    draw_id = st.selectbox(
        "Select Lottery Result",
        options=list(options.keys()),
        format_func=lambda key: (
            f"[{options[key].get('status', '').upper()}] "
            f"{options[key].get('scheme_name') or options[key].get('lottery_name') or 'Unknown'}"
            f" | {options[key].get('result_date')}"
            f" | {options[key].get('draw_time')}"
        ),
        key="delete_pending_selected_draw",
    )

    draw = options[draw_id]
    current_status = draw.get("status")

    # ==========================================
    # LOAD UPLOADED FILE METADATA
    # ==========================================

    try:
        response = (
            admin_client.table("lottery_result_uploads")
            .select("upload_id, file_name, storage_path")
            .eq("draw_id", draw_id)
            .execute()
        )

        uploads = response.data or []

    except Exception as error:
        st.error(
            f"Unable to load uploaded files: {error}"
        )
        return

    # ==========================================
    # DISPLAY DRAW INFORMATION
    # ==========================================

    st.write(
        "**Lottery:**",
        draw.get("scheme_name")
        or draw.get("lottery_name")
        or "N/A",
    )

    st.write(
        "**State:**",
        draw.get("state_name") or "N/A",
    )

    st.write(
        "**Result Date:**",
        draw.get("result_date"),
    )

    st.write(
        "**Draw Time:**",
        draw.get("draw_time"),
    )

    st.write(
        "**Status:**",
        current_status,
    )

    st.write(
        "**Uploaded Files:**",
        len(uploads),
    )

    for upload in uploads:
        st.caption(
            f"📎 {upload.get('file_name') or 'Unnamed file'}"
        )

    # ==========================================
    # DISTINGUISH NEW DELETE FROM RECOVERY
    # ==========================================

    is_recovery = current_status == "deleting"

    if is_recovery:
        st.error(
            "This draw has already been reserved for "
            "deletion. A previous cleanup attempt may "
            "have been interrupted."
        )

        st.info(
            "Recovery will check the remaining uploaded "
            "files, remove any that still exist, and then "
            "attempt database deletion."
        )

        action_label = (
            "🔄 Resume Incomplete Deletion"
        )

        confirmation_label = (
            "Type RESUME DELETE to continue cleanup"
        )

        required_confirmation = "RESUME DELETE"

    else:
        st.warning(
            "This is a new permanent deletion request. "
            "The draw will first be reserved for deletion."
        )

        action_label = (
            "🗑️ Permanently Delete Pending Result"
        )

        confirmation_label = (
            "Type DELETE to confirm permanent deletion"
        )

        required_confirmation = "DELETE"

    # ==========================================
    # EXPLICIT ADMIN CONFIRMATION
    # ==========================================

    with st.form(f"confirm_delete_{draw_id}"):

        confirmation = st.text_input(
            confirmation_label,
            key=f"delete_confirmation_{draw_id}",
        )

        acknowledged = st.checkbox(
            "I understand that this action cannot be undone.",
            key=f"delete_acknowledged_{draw_id}",
        )

        submitted = st.form_submit_button(
            action_label,
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    if (
        confirmation.strip() != required_confirmation
        or not acknowledged
    ):
        st.error(
            f"Action cancelled. Type "
            f"{required_confirmation} exactly and "
            "check the confirmation box."
        )
        return

    # ==========================================
    # EXECUTE PROTECTED DELETION SERVICE
    # ==========================================

    try:
        with st.spinner(
            "Resuming deletion..."
            if is_recovery
            else "Deleting pending result..."
        ):

            result = delete_pending_lottery_result(
                admin_client=admin_client,
                draw_id=draw_id,
            )

        # ======================================
        # CLEAR RELATED SESSION DATA
        # ======================================

        deleted_upload_ids = {
            str(upload["upload_id"])
            for upload in uploads
        }

        if (
            str(st.session_state.get("preview_file_id"))
            in deleted_upload_ids
        ):
            st.session_state.pop(
                "preview_file_id",
                None,
            )

        if (
            str(st.session_state.get("extraction_upload_id"))
            in deleted_upload_ids
            or str(st.session_state.get("reviewed_upload_id"))
            in deleted_upload_ids
            or str(st.session_state.get("reviewed_draw_id"))
            == draw_id
        ):
            for key in (
                "extracted_lottery_data",
                "extraction_upload_id",
                "extraction_validation_errors",
                "extraction_from_cache",
                "reviewed_lottery_data",
                "reviewed_draw_id",
                "reviewed_upload_id",
                "reviewed_expected_counts",
                "review_reference",
            ):
                st.session_state.pop(key, None)

        for upload_id in deleted_upload_ids:
            clear_review_state(upload_id)

        st.session_state.pop(
            f"delete_confirmation_{draw_id}",
            None,
        )

        st.session_state.pop(
            f"delete_acknowledged_{draw_id}",
            None,
        )

        st.session_state["deletion_success_message"] = (
            "Incomplete deletion completed successfully. "
            if is_recovery
            else "Pending lottery result deleted successfully. "
        ) + (
            f"{result['deleted_file_count']} "
            "file(s) removed during this attempt."
        )

        st.rerun()

    except Exception as error:
        st.error(
            f"Deletion operation failed: {error}"
        )

        st.warning(
            "The draw may now be in 'deleting' status. "
            "Refresh this screen to inspect its current "
            "state before attempting recovery. "
            "Do not re-upload or publish this draw."
        )


def show_admin_dashboard():

    st.header("🛡️ NumberDuniya Admin Dashboard")

    # ======================================
    # ADMIN AUTHENTICATION
    # ======================================

    if not st.session_state.get("admin_authenticated"):
        st.error("Access denied. Admin login required.")
        return

    admin_client = st.session_state.get("admin_client")

    if admin_client is None:
        st.error("Admin session missing. Please login again.")
        return

    st.success("Welcome, Administrator!")
    
    # ======================================
    # DELETE SUCCESS MESSAGE
    # ======================================
    
    deletion_message = st.session_state.pop(
        "deletion_success_message",
        None,
    )

    if deletion_message:
        st.success(deletion_message)
    
    # ======================================
    # METADATA UPDATE MESSAGE
    # ======================================  
    
    metadata_message = st.session_state.pop(
        "metadata_update_message",
        None,
    )
    
    
    if metadata_message:
        st.success(metadata_message)

    correction_message = st.session_state.pop(
        "verified_state_correction_message", None
    )
    if correction_message:
        st.success(correction_message)

    publication_message = st.session_state.pop(
        "publication_success_message",
        None,
    )
    if publication_message:
        st.success(publication_message)

    # ======================================
    # DASHBOARD METRICS
    # ======================================

    st.subheader("📋 Administration")

    try:
        metrics = get_dashboard_metrics(admin_client)
    except Exception as error:
        st.error(f"Unable to load dashboard metrics: {error}")
        metrics = None

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Uploaded Results",
            metrics["uploaded_results"] if metrics else "N/A",
        )

    with col2:
        st.metric(
            "Pending Verification",
            metrics["pending_verification"] if metrics else "N/A",
        )

    with col3:
        st.metric(
            "Published Results",
            metrics["published_results"] if metrics else "N/A",
        )

    st.divider()

    # ======================================
    # UPLOADED LOTTERY RESULTS
    # ======================================

    st.subheader("📂 Uploaded Lottery Results")

    try:
        uploaded_results = get_uploaded_results(admin_client)

        if not uploaded_results:
            st.info("No lottery results uploaded yet.")

        else:
            table_data = []

            for record in uploaded_results:
                draw = record.get("lottery_draws") or {}

                raw_time = draw.get("draw_time")
                formatted_time = "N/A"

                if raw_time:
                    try:
                        formatted_time = datetime.strptime(
                            str(raw_time)[:8],
                            "%H:%M:%S",
                        ).strftime("%I:%M %p")
                    except ValueError:
                        formatted_time = str(raw_time)

                table_data.append({
                    "Lottery Name": draw.get("lottery_name"),
                    "Result Date": draw.get("result_date"),
                    "Draw Time": formatted_time,
                    "File Name": record.get("file_name"),
                    "File Type": record.get("file_type"),
                    "Upload Status": record.get("upload_status"),
                    "Verification Status": draw.get("status"),
                    "Uploaded At": record.get("uploaded_at"),
                })

            # Display uploaded results without PyArrow.
            # Workaround for Windows Application Control
            # blocking pyarrow.lib.

            if table_data:
                for index, record in enumerate(table_data, start=1):
                    with st.expander(
                        f"📄 Uploaded Result #{index}",
                        expanded=False,
                    ):
                        for field, value in record.items():
                            st.write(f"**{field}:** {value if value is not None else 'N/A'}")
            else:
                st.info("No uploaded lottery results found.")

            # ==================================
            # SECURE FILE PREVIEW
            # ==================================

            st.subheader("🔎 Preview Uploaded Result")

            preview_options = {
                str(record["upload_id"]): record
                for record in uploaded_results
            }

            selected_preview_id = st.selectbox(
                "Select a file to preview",
                options=list(preview_options.keys()),
                format_func=lambda file_id: (
                    preview_options[file_id].get("file_name") or file_id
                ),
                key="selected_uploaded_preview",
            )

            if st.button("👁️ Preview File", key="open_uploaded_preview"):
                st.session_state["preview_file_id"] = selected_preview_id

            preview_id = st.session_state.get("preview_file_id")

            if preview_id:
                preview_record = preview_options.get(str(preview_id))

                if preview_record is None:
                    st.session_state.pop("preview_file_id", None)
                    st.warning("Selected file is no longer available.")
                else:
                    if st.button("❌ Close Preview", key="close_uploaded_preview"):
                        st.session_state.pop("preview_file_id", None)
                        st.rerun()

                    try:
                        with st.spinner("Loading file securely..."):
                            file_bytes = download_lottery_file(
                                admin_client,
                                preview_record["storage_path"],
                            )

                        if not file_bytes:
                            st.error("The uploaded file is empty.")
                        else:
                            file_name = preview_record.get("file_name") or "lottery-result"
                            mime = str(preview_record.get("file_type") or "").lower()
                            lower_name = file_name.lower()
                            is_pdf = (
                                file_bytes[:5] == b"%PDF-"
                                or mime == "application/pdf"
                                or lower_name.endswith(".pdf")
                            )
                            is_image = (
                                mime in ("image/jpeg", "image/jpg", "image/png", "image/webp")
                                or lower_name.endswith((".jpg", ".jpeg", ".png", ".webp"))
                                or file_bytes.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF"))
                            )

                            if is_pdf:
                                import pymupdf

                                with pymupdf.open(stream=file_bytes, filetype="pdf") as pdf:
                                    page_count = len(pdf)
                                    st.caption(f"PDF: {file_name} | {page_count} page(s)")
                                    page_number = st.number_input(
                                        "Page to preview",
                                        min_value=1,
                                        max_value=page_count,
                                        value=1,
                                        step=1,
                                        key=f"preview_page_{preview_id}",
                                    )
                                    page = pdf.load_page(int(page_number) - 1)
                                    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                                    st.image(
                                        pix.tobytes("png"),
                                        caption=f"{file_name} — Page {page_number} of {page_count}",
                                        width="stretch",
                                    )
                                st.download_button(
                                    "📄 Download Original PDF",
                                    data=file_bytes,
                                    file_name=file_name,
                                    mime="application/pdf",
                                    key=f"preview_pdf_download_{preview_id}",
                                )
                            elif is_image:
                                st.image(file_bytes, caption=file_name, width="stretch")
                            else:
                                st.warning(
                                    f"Unsupported file format: {mime or 'unknown'}. "
                                    "Only PDF, JPEG, PNG, and WebP are supported."
                                )

                    except Exception as error:
                        st.error(f"Unable to preview file: {error}")

    except Exception as error:
        st.error(f"Unable to load uploaded results: {error}")
        st.exception(error)

    st.divider()

    # ======================================
    # ADMIN OPERATIONS
    # ======================================

    st.subheader("⚙️ Admin Operations")

    operation = st.selectbox(
        "Select Operation",
        [
            "PDF Upload",
            "Edit Uploaded Metadata",
            "Correct Verified State",
            "Data Verification",
            "Local OCR Review",
            "Approve & Publish",
            "Audit Logs",
            "Delete Pending Result",
        ],
    )

    if operation == "PDF Upload":
        show_pdf_upload()

    elif operation == "Edit Uploaded Metadata":
        show_edit_lottery_metadata(admin_client)

    elif operation == "Correct Verified State":
        show_correct_verified_state(admin_client)
    
    elif operation == "Delete Pending Result":
        show_delete_pending_result(admin_client)

    elif operation == "Data Verification":

        st.subheader("🤖 AI-Assisted Data Verification")

        try:
            uploaded_results = get_uploaded_results(
                admin_client
            )

            pending_results = [
                record
                for record in uploaded_results
                if (
                    record.get("lottery_draws") or {}
                ).get("status") == "pending"
            ]

            if not pending_results:
                st.info(
                    "No pending lottery results available."
                )

            else:
                result_options = {
                    str(record["upload_id"]): record
                    for record in pending_results
                }

                selected_id = st.selectbox(
                    "Select lottery result for verification",
                    options=list(result_options.keys()),
                    format_func=lambda upload_id: (
                        f"{(result_options[upload_id].get('lottery_draws') or {}).get('lottery_name', 'Unknown')}"
                        f" | {result_options[upload_id]['file_name']}"
                    ),
                )

                selected_record = result_options[
                    selected_id
                ]

                # ==============================
                # TRUSTED DRAW METADATA
                # ==============================

                draw_record = (
                    selected_record.get("lottery_draws") or {}
                )

                required_fields = (
                    "lottery_name",
                    "result_date",
                    "draw_time",
                )

                if not all(
                    draw_record.get(field)
                    for field in required_fields
                ):
                    st.error(
                        "Selected draw metadata is incomplete. "
                        "Extraction cannot proceed."
                    )
                    return

                expected_counts = get_expected_prize_counts(
                    lottery_name=draw_record["lottery_name"],
                    result_date=draw_record["result_date"],
                    draw_time=draw_record["draw_time"],
                )

                if expected_counts is not None:
                    st.info(
                        "📋 Trusted expected-count preset "
                        "available for this draw."
                    )
                else:
                    st.warning(
                        "No trusted count preset configured. "
                        "Admin must confirm expected counts "
                        "from the original result."
                    )

                # ==============================
                # SESSION HELPER
                # ==============================

                def activate_extraction(data, from_cache):
                    if not isinstance(data, dict):
                        raise ValueError(
                            "Extraction must be a JSON object."
                        )

                    errors = validate_extraction_for_draw(
                        data,
                        draw_record,
                        expected_counts,
                    )

                    clear_review_state(selected_id)

                    st.session_state[
                        "extracted_lottery_data"
                    ] = data
                    st.session_state[
                        "extraction_upload_id"
                    ] = selected_id
                    st.session_state[
                        "extraction_validation_errors"
                    ] = errors
                    st.session_state[
                        "extraction_from_cache"
                    ] = from_cache

                    return errors

                # ==============================
                # EXISTING SESSION EXTRACTION
                # ==============================

                has_session_extraction = (
                    st.session_state.get(
                        "extraction_upload_id"
                    ) == selected_id
                    and isinstance(
                        st.session_state.get(
                            "extracted_lottery_data"
                        ),
                        dict,
                    )
                )

                if has_session_extraction:
                    existing_data = st.session_state[
                        "extracted_lottery_data"
                    ]

                    current_errors = validate_extraction_for_draw(
                        existing_data,
                        draw_record,
                        expected_counts,
                    )

                    st.session_state[
                        "extraction_validation_errors"
                    ] = current_errors

                    st.caption(
                        "An extraction is available "
                        "in this session."
                    )

                    # ==========================
                    # MANUAL CACHE SAVE
                    # ==========================

                    if st.button(
                        "💾 Save Existing Extraction to Cache",
                        key=f"save_existing_cache_{selected_id}",
                    ):

                        if expected_counts is None:
                            st.warning(
                                "No trusted count preset exists. "
                                "Draft was not saved."
                            )

                        else:
                            try:
                                cached = get_cached_extraction(
                                    admin_client,
                                    selected_id,
                                    expected_counts=expected_counts,
                                )

                                if cached is not None:
                                    st.info(
                                        "A saved draft already exists "
                                        "for this upload. "
                                        "It will not be overwritten."
                                    )

                                else:
                                    saved = save_extraction_cache(
                                        admin_client=admin_client,
                                        upload_id=selected_id,
                                        extracted_data=existing_data,
                                        expected_counts=expected_counts,
                                    )

                                    if current_errors:
                                        st.warning(
                                            "Draft saved, but validation "
                                            "issues remain. Manual review "
                                            "is required."
                                        )

                                    st.success(
                                        "Session extraction saved as "
                                        f"{saved['extraction_status']} draft."
                                    )

                            except Exception as error:
                                st.error(
                                    f"Unable to save draft: {error}"
                                )

                # ==============================
                # LOAD SAVED DRAFT
                # ==============================

                if st.button(
                    "📦 Load Saved Draft (No Gemini API)",
                    key=f"load_saved_draft_{selected_id}",
                ):
                    try:
                        cached = get_cached_extraction(
                            admin_client,
                            selected_id,
                            expected_counts=expected_counts,
                        )

                        if cached is None:
                            st.info(
                                "No saved draft exists "
                                "for this upload."
                            )

                        else:
                            errors = activate_extraction(
                                cached["extracted_data"],
                                True,
                            )

                            if errors:
                                st.warning(
                                    "Saved draft recovered with "
                                    "validation issues. Review "
                                    "against the original document."
                                )
                            else:
                                st.success(
                                    "Saved draft recovered. "
                                    "Automated checks passed; "
                                    "human verification is still required."
                                )

                    except Exception as error:
                        st.error(
                            "Unable to recover saved draft: "
                            f"{error}"
                        )

                # ==============================
                # CACHE-FIRST GEMINI EXTRACTION
                # ==============================

                if st.button(
                    "🤖 Extract with Gemini AI",
                    key="extract_gemini_ai",
                ):

                    try:
                        with st.spinner(
                            "Checking extraction cache..."
                        ):
                            cached = get_cached_extraction(
                                admin_client,
                                selected_id,
                                expected_counts=expected_counts,
                            )

                        if cached is not None:
                            errors = activate_extraction(
                                cached["extracted_data"],
                                True,
                            )

                            if errors:
                                st.warning(
                                    "Cached draft loaded without "
                                    "a Gemini request. Manual "
                                    "correction is required."
                                )
                            else:
                                st.success(
                                    "Cached extraction loaded. "
                                    "No Gemini API request was needed."
                                )

                        else:
                            with st.spinner(
                                "Gemini AI is analyzing the result..."
                            ):
                                file_bytes = download_lottery_file(
                                    admin_client,
                                    selected_record["storage_path"],
                                )

                                extraction_result = extract_lottery_result(
                                    file_bytes=file_bytes,
                                    file_type=selected_record["file_type"],
                                    expected_counts=expected_counts,
                                )

                            extracted_data = extraction_result[
                                "extracted_data"
                            ]

                            # Preserve session data before database insert.
                            errors = activate_extraction(
                                extracted_data,
                                False,
                            )

                            if expected_counts is None:
                                st.warning(
                                    "Extraction retained in this session, "
                                    "but no trusted count preset exists. "
                                    "Configure a preset before saving "
                                    "a validated draft."
                                )

                            else:
                                try:
                                    saved = save_extraction_cache(
                                        admin_client=admin_client,
                                        upload_id=selected_id,
                                        extracted_data=extracted_data,
                                        expected_counts=expected_counts,
                                    )

                                    st.success(
                                        "Gemini extraction saved "
                                        "persistently as "
                                        f"{saved['extraction_status']}."
                                    )

                                except Exception as save_error:
                                    try:
                                        competing_cache = get_cached_extraction(
                                            admin_client,
                                            selected_id,
                                            expected_counts=expected_counts,
                                        )
                                    except Exception:
                                        competing_cache = None

                                    if competing_cache is not None:
                                        st.info(
                                            "A saved draft already exists. "
                                            "Newly extracted session data "
                                            "was preserved."
                                        )
                                    else:
                                        st.warning(
                                            "Extraction succeeded, but "
                                            "persistent saving failed: "
                                            f"{save_error}. "
                                            "Session data was preserved."
                                        )

                            if errors:
                                st.warning(
                                    "Extraction needs manual review. "
                                    "It has not been approved "
                                    "or published."
                                )

                    except Exception as error:
                        message = str(error)

                        if (
                            "429" in message
                            or "RESOURCE_EXHAUSTED" in message
                        ):
                            st.error(
                                "Gemini API quota exhausted. "
                                "Existing session data was preserved. "
                                "Use 'Load Saved Draft' if a draft "
                                "was previously stored."
                            )
                        else:
                            st.error(
                                "Unable to extract lottery result: "
                                f"{error}"
                            )

                # ==============================
                # ORIGINAL + AI RESULT
                # ==============================

                if (
                    st.session_state.get(
                        "extraction_upload_id"
                    ) == selected_id
                    and isinstance(
                        st.session_state.get(
                            "extracted_lottery_data"
                        ),
                        dict,
                    )
                ):

                    if st.session_state.get(
                        "extraction_from_cache"
                    ):
                        st.info(
                            "📦 Showing cached Gemini extraction. "
                            "Review it against the original result."
                        )

                    validation_errors = st.session_state.get(
                        "extraction_validation_errors",
                        [],
                    )

                    if validation_errors:
                        st.warning(
                            "AI extraction has validation issues. "
                            "Review and correct the extracted data."
                        )

                        for error in validation_errors:
                            st.write(f"• {error}")

                    left_col, right_col = st.columns(
                        [1, 1]
                    )

                    # ==========================
                    # ORIGINAL FILE
                    # ==========================

                    with left_col:
                        st.subheader(
                            "📄 Original Lottery Result"
                        )

                        try:
                            with st.spinner(
                                "Loading original result..."
                            ):
                                original_bytes = download_lottery_file(
                                    admin_client,
                                    selected_record["storage_path"],
                                )

                            original_type = selected_record.get(
                                "file_type"
                            )

                            if original_type in (
                                "image/jpeg",
                                "image/png",
                            ):
                                st.image(
                                    original_bytes,
                                    caption=selected_record[
                                        "file_name"
                                    ],
                                    width="stretch",
                                )

                            elif original_type == "application/pdf":
                                st.download_button(
                                    "📄 Download Original PDF",
                                    data=original_bytes,
                                    file_name=selected_record[
                                        "file_name"
                                    ],
                                    mime="application/pdf",
                                    key="verification_pdf_download",
                                )

                            else:
                                st.warning(
                                    "Unsupported original file format."
                                )

                        except Exception as error:
                            st.error(
                                "Unable to load original: "
                                f"{error}"
                            )

                    # ==========================
                    # EDITABLE EXTRACTION
                    # ==========================

                    with right_col:
                        extracted_data = st.session_state[
                            "extracted_lottery_data"
                        ]

                        prizes = extracted_data.get(
                            "prizes"
                        )

                        if (
                            not isinstance(prizes, list)
                            or any(
                                not isinstance(prize, dict)
                                for prize in prizes
                            )
                        ):
                            st.error(
                                "The extracted draft has an invalid "
                                "prize structure. Verification is "
                                "unavailable until the draft is repaired."
                            )

                        else:
                            show_lottery_verification(
                                extracted_data=extracted_data,
                                draw_id=selected_record["draw_id"],
                                upload_id=selected_record["upload_id"],
                            )

                else:
                    st.info(
                        "Select a result and click "
                        "'Load Saved Draft' or "
                        "'Extract with Gemini AI' to begin."
                    )

        except Exception as error:
            st.error(
                "Unable to load verification data: "
                f"{error}"
            )

    elif operation == "Local OCR Review":
        try:
            show_local_ocr_review(admin_client, get_uploaded_results(admin_client))
        except Exception as error:
            st.error(f"Unable to open local OCR review: {error}")

    elif operation == "Approve & Publish":
        show_publish_results(admin_client)

    elif operation == "Audit Logs":
        st.info("Audit Logs - Coming Soon")