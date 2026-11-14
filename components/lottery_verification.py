
import streamlit as st

from services.lottery_validation_service import (
    validate_lottery_result
)
from services.lottery_verification_service import (
    save_verified_lottery_result,
    validate_draw_metadata
)
from services.lottery_completeness_service import (
    check_lottery_completeness
)
from services.lottery_count_presets import (
    get_expected_prize_counts
)


def clear_saved_review():
    """
    Invalidate previously validated review data.
    """
    for key in (
        "reviewed_lottery_data",
        "reviewed_draw_id",
        "reviewed_upload_id",
        "reviewed_expected_counts"
    ):
        st.session_state.pop(key, None)


def show_lottery_verification(extracted_data, draw_id, upload_id):
    """
    Review AI-extracted or locally extracted lottery results.

    Features:
    - Editable winning numbers
    - Draw-specific expected-count presets
    - Manual counts for unknown draws
    - Completeness validation
    - Metadata matching
    - Final admin approval
    """

    st.subheader("Lottery Result Verification")

    if not st.session_state.get("admin_authenticated"):
        st.error("Admin login required.")
        return

    admin_client = st.session_state.get("admin_client")

    if admin_client is None:
        st.error("Admin session missing.")
        return

    if not draw_id or not upload_id:
        st.error("Draw or upload reference missing.")
        return

    draw_id = str(draw_id)
    upload_id = str(upload_id)

    if st.session_state.get("extraction_upload_id") != upload_id:
        st.error("Selected upload does not match the active extraction.")
        return

    if not isinstance(extracted_data, dict):
        st.error("Invalid extraction data.")
        return

    # ------------------------------------------
    # LOAD SELECTED DRAW METADATA
    # ------------------------------------------

    try:
        draw_response = (
            admin_client.table("lottery_draws")
            .select(
                "draw_id, state_name, lottery_name, "
                "scheme_name, result_date, draw_time, status"
            )
            .eq("draw_id", draw_id)
            .limit(1)
            .execute()
        )

        if not draw_response.data:
            st.error("Selected draw was not found.")
            return

        draw_record = draw_response.data[0]

    except Exception as error:
        st.error(
            f"Unable to load draw metadata: {error}"
        )
        return

    if draw_record.get("status") != "pending":
        st.error(
            "Only pending lottery draws can be reviewed."
        )
        return

    # ------------------------------------------
    # LOAD DRAW-SPECIFIC PRESET
    # ------------------------------------------

    preset_counts = get_expected_prize_counts(
        lottery_name=draw_record.get("lottery_name"),
        result_date=draw_record.get("result_date"),
        draw_time=draw_record.get("draw_time")
    )

    preset_active = preset_counts is not None

    if preset_active:
        st.success(
            "📋 Verified expected-count preset found "
            "for this draw."
        )
        st.caption(
            "Preset counts are locked. They are based "
            "on the configured original-result format."
        )
    else:
        st.info(
            "No expected-count preset is available "
            "for this draw. Enter counts manually "
            "after checking the original document."
        )

    # ------------------------------------------
    # SHOW METADATA
    # ------------------------------------------

    st.write(
        "Lottery:",
        extracted_data.get("lottery_name")
    )
    st.write(
        "Result Date:",
        extracted_data.get("result_date")
    )
    st.write(
        "Draw Time:",
        extracted_data.get("draw_time")
    )

    metadata_errors = validate_draw_metadata(
        extracted_data,
        draw_record
    )

    if metadata_errors:
        st.error(
            "Extraction metadata does not match the selected "
            "Supabase draw."
        )
        for error in metadata_errors:
            st.write(f"• {error}")

    st.divider()
    st.subheader("🏆 Prize-wise Winning Numbers")

    # ------------------------------------------
    # RESET REVIEW WHEN DRAW CHANGES
    # ------------------------------------------

    current_reference = (draw_id, upload_id)

    if st.session_state.get("review_reference") != current_reference:
        clear_saved_review()
        st.session_state["review_reference"] = current_reference

    reviewed_prizes = []
    expected_counts = {}
    missing_expected_counts = []

    # ------------------------------------------
    # ADMIN REVIEW FORM
    # ------------------------------------------

    with st.form(f"lottery_review_form_{upload_id}"):

        for index, prize in enumerate(
            extracted_data.get("prizes", [])
        ):

            category = prize.get(
                "category_name",
                "Unknown Prize"
            )

            st.markdown(f"### {category}")

            numbers = prize.get("winning_numbers") or []

            st.caption(
                f"Extracted: {len(numbers)} "
                "winning number(s)"
            )

            edited_numbers = st.text_area(
                "Winning Numbers (one per line)",
                value="\n".join(numbers),
                key=f"review_numbers_{upload_id}_{index}"
            )

            reviewed_numbers = [
                number.strip()
                for number in edited_numbers.splitlines()
                if number.strip()
            ]

            st.caption(
                f"✏️ Admin Reviewed: {len(reviewed_numbers)} "
                "winning number(s)"
            )

            if len(reviewed_numbers) != len(numbers):
                st.warning(
                    "Winning number count has changed. "
                    "Compare all entries with the original result."
                )

            # ------------------------------------------
            # EXPECTED COUNT: PRESET OR MANUAL
            # ------------------------------------------

            if preset_active:

                if category in preset_counts:
                    expected_value = preset_counts[category]

                    st.number_input(
                        "Expected winning-number count "
                        "(verified preset)",
                        min_value=0,
                        value=expected_value,
                        step=1,
                        disabled=True,
                        key=f"preset_count_{upload_id}_{index}"
                    )

                    expected_counts[category] = expected_value

                else:
                    st.error(
                        f"No preset count configured for "
                        f"'{category}'."
                    )
                    missing_expected_counts.append(category)

            else:

                expected_input = st.text_input(
                    "Expected winning-number count "
                    "(confirm from original result)",
                    value="",
                    key=f"expected_count_{upload_id}_{index}",
                    placeholder="Enter independently confirmed count"
                )

                expected_text = expected_input.strip()

                if expected_text.isdigit():
                    expected_counts[category] = int(expected_text)
                else:
                    missing_expected_counts.append(category)

            reviewed_prizes.append({
                "category_name": category,
                "prize_amount": prize.get("prize_amount"),
                "winning_numbers": reviewed_numbers
            })

        submitted = st.form_submit_button(
            "🔍 Validate Reviewed Results & Completeness"
        )

    current_reviewed_data = {
        **extracted_data,
        "prizes": reviewed_prizes
    }

    # ------------------------------------------
    # VALIDATE REVIEWED DATA
    # ------------------------------------------

    if submitted:

        clear_saved_review()

        structural_errors = validate_lottery_result(
            current_reviewed_data
        )

        if structural_errors:
            for error in structural_errors:
                st.error(error)

        elif metadata_errors:
            st.error(
                "Metadata mismatch detected. "
                "Verification cannot proceed."
            )

        elif missing_expected_counts:
            st.error(
                "Expected counts are missing for "
                "one or more prize categories."
            )
            for category in missing_expected_counts:
                st.write(f"• {category}")

        else:

            try:
                # Use full preset to detect missing
                # prize categories as well.
                counts_to_check = (
                    preset_counts
                    if preset_active
                    else expected_counts
                )

                completeness_result = (
                    check_lottery_completeness(
                        current_reviewed_data,
                        counts_to_check
                    )
                )

                st.subheader(
                    "📊 Prize-wise Completeness Report"
                )

                report_rows = []

                for item in completeness_result["results"]:
                    report_rows.append({
                        "Prize": item["category"],
                        "Expected": item["expected"],
                        "Reviewed": item["actual"],
                        "Status": (
                            "PASS"
                            if item["matched"]
                            else "FAIL"
                        )
                    })

                # Render with native Streamlit widgets: st.dataframe may
                # import PyArrow, whose DLL is blocked by Windows policy.
                header_cols = st.columns([3, 1, 1, 1])
                for col, heading in zip(
                    header_cols, ("Prize", "Expected", "Reviewed", "Status")
                ):
                    col.markdown(f"**{heading}**")

                for report_row in report_rows:
                    row_cols = st.columns([3, 1, 1, 1])
                    row_cols[0].write(str(report_row["Prize"]))
                    row_cols[1].write(str(report_row["Expected"]))
                    row_cols[2].write(str(report_row["Reviewed"]))
                    row_cols[3].write(str(report_row["Status"]))

                if completeness_result["unexpected_categories"]:
                    st.error(
                        "Unexpected prize categories: "
                        + ", ".join(
                            completeness_result[
                                "unexpected_categories"
                            ]
                        )
                    )

                if not completeness_result["all_matched"]:
                    st.error(
                        "Completeness validation failed. "
                        "Review missing or extra winning numbers."
                    )

                else:

                    st.session_state[
                        "reviewed_lottery_data"
                    ] = current_reviewed_data

                    st.session_state[
                        "reviewed_draw_id"
                    ] = draw_id

                    st.session_state[
                        "reviewed_upload_id"
                    ] = upload_id

                    st.session_state[
                        "reviewed_expected_counts"
                    ] = dict(counts_to_check)

                    st.success(
                        "Structural validation, metadata matching "
                        "and prize-wise count checks passed!"
                    )

            except Exception as error:
                st.error(
                    f"Completeness validation failed: {error}"
                )

    # ------------------------------------------
    # FINAL APPROVAL ELIGIBILITY
    # ------------------------------------------

    reviewed_data = st.session_state.get(
        "reviewed_lottery_data"
    )

    saved_expected_counts = st.session_state.get(
        "reviewed_expected_counts"
    )

    current_expected_counts = (
        preset_counts
        if preset_active
        else expected_counts
    )

    review_matches = (
        reviewed_data is not None
        and st.session_state.get("reviewed_draw_id") == draw_id
        and st.session_state.get("reviewed_upload_id") == upload_id
        and reviewed_data == current_reviewed_data
        and saved_expected_counts == current_expected_counts
        and not missing_expected_counts
        and not metadata_errors
    )

    if review_matches:

        st.divider()
        st.subheader("✅ Final Verification Approval")

        st.warning(
            "Count matching does not prove individual "
            "ticket-number accuracy. Compare every "
            "winning number, prize amount, category "
            "and draw detail with the original result."
        )

        confirmed = st.checkbox(
            "I have manually compared all reviewed "
            "data with the original result.",
            key=f"verification_confirm_{upload_id}"
        )

        if st.button(
            "✅ Approve Verification",
            disabled=not confirmed,
            key=f"approve_verification_{upload_id}"
        ):

            try:
                final_errors = validate_lottery_result(
                    reviewed_data
                )

                final_metadata_errors = (
                    validate_draw_metadata(
                        reviewed_data,
                        draw_record
                    )
                )

                final_completeness = (
                    check_lottery_completeness(
                        reviewed_data,
                        current_expected_counts
                    )
                )

                if (
                    final_errors
                    or final_metadata_errors
                    or not final_completeness["all_matched"]
                ):
                    st.error(
                        "Final validation failed. "
                        "Approval cancelled."
                    )
                    return

                with st.spinner(
                    "Saving verified lottery result..."
                ):
                    save_verified_lottery_result(
                        admin_client=admin_client,
                        draw_id=draw_id,
                        upload_id=upload_id,
                        reviewed_data=reviewed_data
                    )

                st.success(
                    "Lottery result verified successfully!"
                )

                clear_saved_review()

                for key in (
                    "review_reference",
                    "extracted_lottery_data",
                    "extraction_upload_id",
                    "extraction_validation_errors",
                    "extraction_from_cache"
                ):
                    st.session_state.pop(key, None)

                st.rerun()

            except Exception as error:
                st.error(
                    f"Verification failed: {error}"
                )
