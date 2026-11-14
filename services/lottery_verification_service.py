
from datetime import datetime
from uuid import UUID

from services.lottery_validation_service import (
    validate_lottery_result
)


def normalize_lottery_name(value):
    """
    Normalize harmless whitespace and case differences.
    Do not remove meaningful words or characters.
    """
    if not isinstance(value, str):
        return ""

    return " ".join(value.split()).casefold()


def normalize_draw_time(value):
    """
    Normalize valid HH:MM or HH:MM:SS time strings
    to HH:MM:SS for comparison.
    """
    if not isinstance(value, str):
        raise ValueError("Invalid draw time.")

    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(
                value,
                time_format
            )
            return parsed.strftime("%H:%M:%S")
        except ValueError:
            continue

    raise ValueError("Invalid draw time.")


def validate_draw_metadata(reviewed_data, draw_record):
    """
    Compare reviewed lottery metadata with the
    selected draw stored in Supabase.

    Identity: lottery_name + result_date + draw_time.
    scheme_name is optional descriptive metadata.

    Returns a list of mismatch errors.
    """

    errors = []

    if not isinstance(draw_record, dict):
        return ["Invalid Supabase draw record."]

    if not isinstance(reviewed_data, dict):
        return ["Invalid reviewed lottery data."]

    # ------------------------------------------
    # LOTTERY NAME VALIDATION
    # The lottery operator/name is the draw identity.
    # Scheme is optional descriptive metadata, not its identity.
    # ------------------------------------------

    expected_name = normalize_lottery_name(draw_record.get("lottery_name"))
    reviewed_name = normalize_lottery_name(reviewed_data.get("lottery_name"))

    if not expected_name or not reviewed_name:
        errors.append("Lottery name is missing in the draw or reviewed result.")
    elif expected_name != reviewed_name:
        errors.append("Lottery name mismatch between uploaded draw and reviewed result.")

    # ------------------------------------------
    # RESULT DATE VALIDATION
    # ------------------------------------------

    database_date = draw_record.get("result_date")
    reviewed_date = reviewed_data.get("result_date")

    if database_date != reviewed_date:
        errors.append(
            "Result date mismatch between uploaded "
            "draw and reviewed result."
        )

    # ------------------------------------------
    # DRAW TIME VALIDATION
    # ------------------------------------------

    try:
        database_time = normalize_draw_time(
            draw_record.get("draw_time")
        )

        reviewed_time = normalize_draw_time(
            reviewed_data.get("draw_time")
        )

        if database_time != reviewed_time:
            errors.append(
                "Draw time mismatch between uploaded "
                "draw and reviewed result."
            )

    except ValueError:
        errors.append(
            "Invalid draw time in reviewed data "
            "or Supabase draw record."
        )

    return errors


def save_verified_lottery_result(
    admin_client,
    draw_id,
    upload_id,
    reviewed_data
):
    """
    Validate and save reviewed lottery results
    using the secure upload-bound PostgreSQL RPC.
    """

    if admin_client is None:
        raise ValueError("Admin client is required.")

    # ------------------------------------------
    # VALIDATE UUID REFERENCES
    # ------------------------------------------

    try:
        valid_draw_id = str(UUID(str(draw_id)))
        valid_upload_id = str(UUID(str(upload_id)))

    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "Invalid draw ID or upload ID."
        )

    # ------------------------------------------
    # VALIDATE REVIEWED JSON
    # ------------------------------------------

    validation_errors = validate_lottery_result(
        reviewed_data
    )

    if validation_errors:
        raise ValueError(
            "Validation failed: "
            + "; ".join(validation_errors)
        )

    # ------------------------------------------
    # FETCH ORIGINAL DRAW METADATA
    # ------------------------------------------

    draw_response = (
        admin_client.table("lottery_draws")
        .select(
            "draw_id, state_name, lottery_name, "
            "scheme_name, result_date, draw_time, status"
        )
        .eq("draw_id", valid_draw_id)
        .limit(1)
        .execute()
    )

    if not draw_response.data:
        raise ValueError(
            "Selected lottery draw was not found."
        )

    draw_record = draw_response.data[0]

    if draw_record.get("status") != "pending":
        raise ValueError(
            "Only pending lottery draws can be verified."
        )

    # ------------------------------------------
    # COMPARE METADATA
    # ------------------------------------------

    metadata_errors = validate_draw_metadata(
        reviewed_data,
        draw_record
    )

    if metadata_errors:
        raise ValueError(
            "Lottery metadata verification failed: "
            + "; ".join(metadata_errors)
        )

    # ------------------------------------------
    # SECURE DATABASE VERIFICATION
    # ------------------------------------------

    # The RPC independently checks:
    # - Admin authorization
    # - Upload/draw binding
    # - Pending draw status
    # - Atomic database writes

    admin_client.rpc(
        "verify_uploaded_lottery_result",
        {
            "p_upload_id": valid_upload_id,
            "p_draw_id": valid_draw_id,
            "p_prizes": reviewed_data["prizes"]
        }
    ).execute()

    return {
        "success": True,
        "upload_id": valid_upload_id,
        "draw_id": valid_draw_id,
        "status": "verified"
    }
