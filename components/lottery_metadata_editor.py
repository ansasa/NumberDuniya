
from datetime import date, datetime

import streamlit as st


def show_lottery_metadata_editor(admin_client):
    """
    Edit metadata of pending lottery draws only.

    Uses the authenticated Supabase client.
    Database RLS must authorize admin updates.
    """

    st.subheader("✏️ Edit Uploaded Lottery Metadata")

    st.info(
        "Correct uploaded lottery metadata using the "
        "original lottery result. Only pending draws "
        "can be edited."
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

        pending_draws = response.data or []

    except Exception as error:
        st.error(f"Unable to load pending draws: {error}")
        return

    if not pending_draws:
        st.info("No pending lottery results available.")
        return

    draw_options = {
        str(draw["draw_id"]): draw
        for draw in pending_draws
    }

    selected_draw_id = st.selectbox(
        "Select Pending Lottery Draw",
        options=list(draw_options.keys()),
        format_func=lambda draw_id: (
            f"{draw_options[draw_id].get('lottery_name') or 'Unknown'} "
            f"| {draw_options[draw_id].get('result_date') or 'N/A'}"
        ),
        key="metadata_selected_draw"
    )

    selected_draw = draw_options[selected_draw_id]

    try:
        existing_date = date.fromisoformat(
            str(selected_draw["result_date"])
        )

        existing_time = datetime.strptime(
            str(selected_draw["draw_time"])[:8],
            "%H:%M:%S"
        ).time()

    except (ValueError, TypeError, KeyError):
        st.error(
            "Existing date or time is invalid. "
            "Cannot safely open the editor."
        )
        return

    st.warning(
        "Verify every field against the original document. "
        "Changes to uploaded metadata do not automatically "
        "correct Gemini's extracted draft."
    )

    with st.form(
        key=f"edit_metadata_form_{selected_draw_id}"
    ):

        state_name = st.text_input(
            "State",
            value=selected_draw.get("state_name") or ""
        )

        lottery_name = st.text_input(
            "Lottery Operator / Name",
            value=selected_draw.get("lottery_name") or ""
        )

        scheme_name = st.text_input(
            "Lottery Scheme",
            value=selected_draw.get("scheme_name") or ""
        )

        result_date = st.date_input(
            "Result Date",
            value=existing_date,
            format="DD/MM/YYYY"
        )

        draw_time = st.time_input(
            "Draw Time",
            value=existing_time,
            step=60
        )

        draw_number = st.text_input(
            "Draw Number",
            value=str(
                selected_draw.get("draw_number") or ""
            )
        )

        confirmed = st.checkbox(
            "I have checked these details against "
            "the original lottery result."
        )

        submitted = st.form_submit_button(
            "💾 Save Metadata Changes",
            use_container_width=True
        )

    if not submitted:
        return

    if not confirmed:
        st.warning(
            "Please confirm that you checked "
            "the original result."
        )
        return

    if not lottery_name.strip():
        st.error("Lottery operator/name is required.")
        return

    if not scheme_name.strip():
        st.error("Lottery scheme is required.")
        return

    if not state_name.strip():
        st.error("State is required.")
        return

    updated_metadata = {
        "state_name": state_name.strip(),
        "lottery_name": lottery_name.strip(),
        "scheme_name": scheme_name.strip(),
        "result_date": result_date.isoformat(),
        "draw_time": draw_time.strftime("%H:%M:%S"),
        "draw_number": draw_number.strip() or None
    }

    try:
        # Recheck status immediately before update.
        latest = (
            admin_client.table("lottery_draws")
            .select("draw_id, status")
            .eq("draw_id", selected_draw_id)
            .limit(1)
            .execute()
        )

        if (
            not latest.data
            or latest.data[0].get("status") != "pending"
        ):
            st.error(
                "This draw is no longer pending. "
                "Metadata was not updated."
            )
            return

        # Status filter prevents updating a draw
        # that is already verified or published.
        update_response = (
            admin_client.table("lottery_draws")
            .update(updated_metadata)
            .eq("draw_id", selected_draw_id)
            .eq("status", "pending")
            .execute()
        )

        if not update_response.data:
            st.error(
                "No draw was updated. Check database "
                "permissions and current draw status."
            )
            return

        # Existing extraction may contain stale metadata.
        # Remove session draft to prevent accidental reuse.
        st.session_state.pop(
            "extracted_lottery_data", None
        )
        st.session_state.pop(
            "extraction_upload_id", None
        )
        st.session_state.pop(
            "extraction_validation_errors", None
        )
        st.session_state.pop(
            "extraction_from_cache", None
        )

        st.session_state["metadata_update_message"] = (
            "Lottery metadata updated successfully. "
            "Review the AI-extracted metadata separately "
            "before verification."
        )

        st.rerun()

    except Exception as error:
        st.error(
            "Unable to update lottery metadata. "
            f"Database response: {error}"
        )
