
from uuid import UUID

from services.lottery_validation_service import (
    validate_lottery_result,
)
from services.gemini_extraction_service import (
    validate_extraction_completeness,
)
from services.lottery_verification_service import (
    validate_draw_metadata,
)
from services.lottery_count_presets import (
    get_expected_prize_counts,
)


CACHE_TABLE = "lottery_extraction_cache"
UPLOAD_TABLE = "lottery_result_uploads"
DRAW_TABLE = "lottery_draws"

MODEL_NAME = "gemini-2.5-flash"

VALID_STATUSES = {
    "unverified",
    "needs_review",
    "validated",
}


def _validate_upload_id(upload_id):
    """Validate and normalize upload UUID."""

    try:
        return str(UUID(str(upload_id)))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError(
            "Invalid upload ID."
        ) from error


def _normalize_errors(errors):
    """Normalize validator output into error strings."""

    if errors is None:
        return []

    if isinstance(errors, str):
        return [errors] if errors else []

    if not isinstance(errors, (list, tuple)):
        raise TypeError(
            "Validator must return a list of errors."
        )

    return [
        str(error)
        for error in errors
        if error
    ]


def _run_validation(label, validator):
    """Convert validation exceptions into reviewable errors."""

    try:
        return _normalize_errors(validator())
    except (ValueError, TypeError, KeyError) as error:
        return [f"{label}: {error}"]


def _get_trusted_draw(admin_client, upload_id):
    """
    Retrieve trusted draw metadata from Supabase.

    Gemini-extracted metadata is never used as
    the source of truth for this lookup.

    Database errors are propagated.
    """

    upload_response = (
        admin_client.table(UPLOAD_TABLE)
        .select("upload_id, draw_id")
        .eq("upload_id", upload_id)
        .limit(1)
        .execute()
    )

    if not upload_response.data:
        raise ValueError(
            "Upload not found or not accessible."
        )

    draw_id = upload_response.data[0].get("draw_id")

    if not draw_id:
        raise ValueError(
            "Upload has no associated draw."
        )

    draw_response = (
        admin_client.table(DRAW_TABLE)
        .select(
            "draw_id, lottery_name, "
            "result_date, draw_time, status"
        )
        .eq("draw_id", str(draw_id))
        .limit(1)
        .execute()
    )

    if not draw_response.data:
        raise ValueError(
            "Trusted lottery draw not found or not accessible."
        )

    draw_record = draw_response.data[0]

    required_fields = (
        "lottery_name",
        "result_date",
        "draw_time",
    )

    if not all(
        draw_record.get(field)
        for field in required_fields
    ):
        raise ValueError(
            "Trusted draw metadata is incomplete."
        )

    return draw_record


def _get_trusted_expected_counts(draw_record):
    """
    Resolve expected counts using trusted draw
    metadata and independently configured presets.

    Never derive expected counts from Gemini data
    or caller-supplied expected_counts.

    Unknown draws return None.
    """

    return get_expected_prize_counts(
        lottery_name=str(
            draw_record["lottery_name"]
        ),
        result_date=str(
            draw_record["result_date"]
        ),
        draw_time=str(
            draw_record["draw_time"]
        ),
    )


def _validate_extraction(
    extracted_data,
    expected_counts=None,
    draw_record=None,
):
    """
    Validate structure, completeness and metadata.

    Invalid extraction drafts remain saveable.

    Returns:
        structural_errors,
        completeness_errors,
        metadata_errors,
        combined_errors
    """

    if not isinstance(extracted_data, dict):
        raise ValueError(
            "Extracted data must be a dictionary."
        )

    structural_errors = _run_validation(
        "Structural validation failed",
        lambda: validate_lottery_result(
            extracted_data
        ),
    )

    completeness_errors = _run_validation(
        "Completeness validation failed",
        lambda: validate_extraction_completeness(
            extracted_data,
            expected_counts=expected_counts,
        ),
    )

    if draw_record is None:
        metadata_errors = []
    else:
        metadata_errors = _run_validation(
            "Draw metadata validation failed",
            lambda: validate_draw_metadata(
                extracted_data,
                draw_record,
            ),
        )

    combined_errors = list(
        dict.fromkeys(
            structural_errors
            + completeness_errors
            + metadata_errors
        )
    )

    return (
        structural_errors,
        completeness_errors,
        metadata_errors,
        combined_errors,
    )


def _determine_status(
    validation_errors,
    expected_counts,
    trusted_metadata_checked,
):
    """
    Decide automated extraction status.

    Errors -> needs_review

    No errors, but no trusted counts or metadata
    -> unverified

    All trusted checks passed -> validated
    """

    if validation_errors:
        return "needs_review"

    if (
        expected_counts is None
        or not trusted_metadata_checked
    ):
        return "unverified"

    return "validated"


def get_cached_extraction(
    admin_client,
    upload_id,
    expected_counts=None,
):
    """
    Retrieve and revalidate a cached extraction.

    expected_counts is retained for compatibility
    but is NOT trusted for validation.

    Previously unverified or needs_review records
    are never silently promoted to validated.

    Returns None when no cache exists.
    """

    if admin_client is None:
        raise ValueError(
            "Admin client is required."
        )

    valid_upload_id = _validate_upload_id(
        upload_id
    )

    response = (
        admin_client.table(CACHE_TABLE)
        .select(
            "extracted_data, model_name, "
            "created_at, updated_at, "
            "extraction_status, validation_errors"
        )
        .eq("upload_id", valid_upload_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    record = response.data[0]

    cached_data = record.get(
        "extracted_data"
    )

    if not isinstance(cached_data, dict):
        raise ValueError(
            "Cached extraction must be a JSON object."
        )

    # Independently retrieve trusted draw metadata.
    draw_record = _get_trusted_draw(
        admin_client,
        valid_upload_id,
    )

    # Use only independently configured counts.
    trusted_counts = _get_trusted_expected_counts(
        draw_record
    )

    (
        structural_errors,
        completeness_errors,
        metadata_errors,
        current_errors,
    ) = _validate_extraction(
        cached_data,
        expected_counts=trusted_counts,
        draw_record=draw_record,
    )

    stored_status = record.get(
        "extraction_status",
        "unverified",
    )

    if stored_status not in VALID_STATUSES:
        raise ValueError(
            "Invalid cached extraction status."
        )

    stored_errors = record.get(
        "validation_errors"
    )

    if not isinstance(stored_errors, list):
        stored_errors = []

    current_status = _determine_status(
        validation_errors=current_errors,
        expected_counts=trusted_counts,
        trusted_metadata_checked=True,
    )

    # Never silently promote an older draft.
    if current_status == "validated":
        effective_status = (
            "validated"
            if stored_status == "validated"
            else "unverified"
        )
    else:
        effective_status = current_status

    return {
        "extracted_data": cached_data,
        "validation_errors": current_errors,
        "structural_errors": structural_errors,
        "completeness_errors": completeness_errors,
        "metadata_errors": metadata_errors,
        "stored_validation_errors": stored_errors,
        "extraction_status": effective_status,
        "stored_status": stored_status,
        "is_complete": not current_errors,
        "model_name": record.get("model_name"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "from_cache": True,
    }


def save_extraction_cache(
    admin_client,
    upload_id,
    extracted_data,
    expected_counts=None,
):
    """
    Save an extraction as a persistent draft.

    expected_counts remains an accepted parameter
    for backward compatibility, but is ignored
    for trusted validation.

    Trusted expected counts are derived from
    Supabase draw metadata and local presets.

    needs_review:
        Structural, completeness or metadata
        validation failed.

    unverified:
        No detected errors, but trusted counts
        are unavailable.

    validated:
        Structural, completeness and trusted
        metadata checks passed using trusted counts.

    Existing cache records are not overwritten.

    This function does not approve or publish
    lottery results.
    """

    if admin_client is None:
        raise ValueError(
            "Admin client is required."
        )

    valid_upload_id = _validate_upload_id(
        upload_id
    )

    # Fail closed if trusted draw cannot be loaded.
    draw_record = _get_trusted_draw(
        admin_client,
        valid_upload_id,
    )

    # Never trust caller-provided expected counts.
    trusted_counts = _get_trusted_expected_counts(
        draw_record
    )

    (
        structural_errors,
        completeness_errors,
        metadata_errors,
        validation_errors,
    ) = _validate_extraction(
        extracted_data,
        expected_counts=trusted_counts,
        draw_record=draw_record,
    )

    extraction_status = _determine_status(
        validation_errors=validation_errors,
        expected_counts=trusted_counts,
        trusted_metadata_checked=True,
    )

    response = (
        admin_client.table(CACHE_TABLE)
        .insert({
            "upload_id": valid_upload_id,
            "extracted_data": extracted_data,
            "model_name": MODEL_NAME,
            "extraction_status": extraction_status,
            "validation_errors": validation_errors,
        })
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Extraction cache insert failed."
        )

    return {
        "success": True,
        "upload_id": valid_upload_id,
        "extraction_status": extraction_status,
        "validation_errors": validation_errors,
        "structural_errors": structural_errors,
        "completeness_errors": completeness_errors,
        "metadata_errors": metadata_errors,
        "is_complete": not validation_errors,
        "from_cache": False,
    }
