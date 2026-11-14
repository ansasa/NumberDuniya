
import uuid
from datetime import date, datetime, time

BUCKET_NAME = "lottery-results-pdfs"

ALLOWED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

MAX_FILE_SIZE = 10 * 1024 * 1024

ACTIVE_DRAW_STATUSES = {
    "pending",
    "verified",
    "published",
    "deleting",
}


class DuplicateLotteryDrawError(ValueError):
    """Raised when a lottery draw already exists."""


def _normalize_lottery_name(lottery_name):
    if not isinstance(lottery_name, str):
        raise ValueError("Lottery name must be a string.")

    normalized = " ".join(lottery_name.split())

    if not normalized:
        raise ValueError("Lottery name is required.")

    return normalized


def _normalize_result_date(result_date):
    if isinstance(result_date, datetime):
        return result_date.date().isoformat()

    if isinstance(result_date, date):
        return result_date.isoformat()

    try:
        return date.fromisoformat(
            str(result_date)
        ).isoformat()
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Invalid result date. Expected YYYY-MM-DD."
        ) from error


def _normalize_draw_time(draw_time):
    if isinstance(draw_time, datetime):
        return draw_time.time().replace(
            microsecond=0
        ).isoformat()

    if isinstance(draw_time, time):
        return draw_time.replace(
            microsecond=0
        ).isoformat()

    value = str(draw_time).strip()

    try:
        return time.fromisoformat(
            value
        ).replace(microsecond=0).isoformat()
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Invalid draw time. Expected HH:MM:SS."
        ) from error


def _validate_admin_client(admin_client):
    if admin_client is None:
        raise ValueError(
            "Authenticated admin client is required."
        )


def _validate_file(file_name, file_bytes):
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("File name is required.")

    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise ValueError(
            "Cannot upload an empty or invalid file."
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(
            "File exceeds the 10 MB limit."
        )

    extension = "." + file_name.rsplit(
        ".", 1
    )[-1].lower()

    if extension not in ALLOWED_MIME_TYPES:
        raise ValueError("Unsupported file type.")

    mime_type = ALLOWED_MIME_TYPES[extension]

    signatures = {
        "application/pdf": b"%PDF-",
        "image/jpeg": b"\xff\xd8\xff",
        "image/png": b"\x89PNG\r\n\x1a\n",
    }

    if not file_bytes.startswith(signatures[mime_type]):
        raise ValueError(
            "File content does not match its extension."
        )

    return extension, mime_type


def find_existing_lottery_draw(
    admin_client,
    lottery_name,
    result_date,
    draw_time,
):
    """
    Check for an existing draw using lottery identity.

    This function is read-only.

    Comparison ignores lottery-name casing and
    repeated whitespace.

    Database errors are not suppressed.
    """

    _validate_admin_client(admin_client)

    normalized_name = _normalize_lottery_name(
        lottery_name
    )
    normalized_date = _normalize_result_date(
        result_date
    )
    normalized_time = _normalize_draw_time(
        draw_time
    )

    response = (
        admin_client.table("lottery_draws")
        .select(
            "draw_id, lottery_name, "
            "result_date, draw_time, status"
        )
        .eq("result_date", normalized_date)
        .eq("draw_time", normalized_time)
        .execute()
    )

    for record in response.data or []:
        existing_name = " ".join(
            str(
                record.get("lottery_name") or ""
            ).split()
        )

        if (
            existing_name.casefold()
            == normalized_name.casefold()
        ):
            return record

    return None


def _raise_if_duplicate(
    admin_client,
    lottery_name,
    result_date,
    draw_time,
):
    existing = find_existing_lottery_draw(
        admin_client=admin_client,
        lottery_name=lottery_name,
        result_date=result_date,
        draw_time=draw_time,
    )

    if existing is None:
        return

    status = str(
        existing.get("status") or "unknown"
    ).lower()

    draw_id = existing.get("draw_id")

    if status == "published":
        guidance = (
            "This lottery result is already published."
        )
    elif status == "pending":
        guidance = (
            "This lottery result is already pending. "
            "Review the existing upload instead."
        )
    elif status == "verified":
        guidance = (
            "This lottery result is already verified. "
            "Use the existing draw for publication."
        )
    elif status == "deleting":
        guidance = (
            "Deletion is in progress for this draw. "
            "Complete or resume deletion first."
        )
    else:
        guidance = (
            "An existing draw was found. "
            "Please review it before uploading."
        )

    raise DuplicateLotteryDrawError(
        f"{guidance} "
        f"Existing Draw ID: {draw_id}"
    )


def upload_lottery_file(
    admin_client,
    file_name,
    file_bytes,
):
    """
    Upload a valid result file to private Storage.
    """

    _validate_admin_client(admin_client)

    extension, mime_type = _validate_file(
        file_name,
        file_bytes,
    )

    unique_name = f"{uuid.uuid4()}{extension}"
    storage_path = f"lottery-results/{unique_name}"

    admin_client.storage.from_(
        BUCKET_NAME
    ).upload(
        path=storage_path,
        file=file_bytes,
        file_options={
            "content-type": mime_type,
            "upsert": "false",
        },
    )

    return {
        "storage_path": storage_path,
        "file_name": file_name,
        "file_type": mime_type,
    }


def create_lottery_draw(
    admin_client,
    lottery_name,
    result_date,
    draw_time,
):
    """
    Create a pending lottery draw.

    Existing database uniqueness remains the
    final protection against duplicate inserts.
    """

    _validate_admin_client(admin_client)

    normalized_name = _normalize_lottery_name(
        lottery_name
    )
    normalized_date = _normalize_result_date(
        result_date
    )
    normalized_time = _normalize_draw_time(
        draw_time
    )

    _raise_if_duplicate(
        admin_client,
        normalized_name,
        normalized_date,
        normalized_time,
    )

    try:
        result = (
            admin_client.table("lottery_draws")
            .insert({
                "lottery_name": normalized_name,
                "result_date": normalized_date,
                "draw_time": normalized_time,
                "status": "pending",
            })
            .execute()
        )
    except Exception as error:
        error_text = str(error).lower()

        if (
            "23505" in error_text
            or "unique_lottery_draw" in error_text
            or "duplicate key" in error_text
        ):
            raise DuplicateLotteryDrawError(
                "This lottery draw already exists. "
                "Duplicate upload was prevented."
            ) from error

        raise

    if not result.data:
        raise RuntimeError(
            "Draw creation did not return a draw ID."
        )

    return result.data[0]["draw_id"]


def save_lottery_upload_metadata(
    admin_client,
    draw_id,
    file_name,
    storage_path,
    file_type,
):
    """
    Save upload metadata using the authenticated
    admin client.
    """

    _validate_admin_client(admin_client)

    if not draw_id:
        raise ValueError("Draw ID is required.")

    if not file_name or not storage_path:
        raise ValueError(
            "File name and storage path are required."
        )

    if file_type not in ALLOWED_MIME_TYPES.values():
        raise ValueError("Unsupported file type.")

    user_response = admin_client.auth.get_user()
    user = user_response.user

    if not user:
        raise PermissionError(
            "Authenticated user session is required."
        )

    result = (
        admin_client.table("lottery_result_uploads")
        .insert({
            "draw_id": str(draw_id),
            "file_name": file_name,
            "storage_path": storage_path,
            "file_type": file_type,
            "uploaded_by": user.id,
            "upload_status": "uploaded",
        }, returning="minimal")
        .execute()
    )

    return {
        "success": True,
        "draw_id": str(draw_id),
        "storage_path": storage_path,
        "file_type": file_type,
    }


def process_lottery_result_upload(
    admin_client,
    lottery_name,
    result_date,
    draw_time,
    file_name,
    file_bytes,
):
    """
    Validate input, prevent duplicate draw creation,
    upload the file, and save metadata.

    On failure, attempt safe Storage cleanup.

    A newly created pending draw may require
    the existing secure deletion workflow if
    database cleanup cannot be completed.
    """

    _validate_admin_client(admin_client)

    normalized_name = _normalize_lottery_name(
        lottery_name
    )
    normalized_date = _normalize_result_date(
        result_date
    )
    normalized_time = _normalize_draw_time(
        draw_time
    )

    # Validate file BEFORE creating a database row.
    _validate_file(file_name, file_bytes)

    # Friendly duplicate check BEFORE creating a draw.
    _raise_if_duplicate(
        admin_client,
        normalized_name,
        normalized_date,
        normalized_time,
    )

    draw_id = None
    storage_path = None

    try:
        draw_id = create_lottery_draw(
            admin_client=admin_client,
            lottery_name=normalized_name,
            result_date=normalized_date,
            draw_time=normalized_time,
        )

        uploaded = upload_lottery_file(
            admin_client=admin_client,
            file_name=file_name,
            file_bytes=file_bytes,
        )

        storage_path = uploaded["storage_path"]

        metadata = save_lottery_upload_metadata(
            admin_client=admin_client,
            draw_id=draw_id,
            file_name=uploaded["file_name"],
            storage_path=storage_path,
            file_type=uploaded["file_type"],
        )

        return {
            "success": True,
            "draw_id": draw_id,
            "storage_path": storage_path,
            "file_type": uploaded["file_type"],
            "metadata": metadata,
        }

    except DuplicateLotteryDrawError:
        raise

    except Exception as error:
        cleanup_errors = []

        # Attempt to remove the uploaded Storage object.
        if storage_path:
            try:
                admin_client.storage.from_(
                    BUCKET_NAME
                ).remove([storage_path])
            except Exception as cleanup_error:
                cleanup_errors.append(
                    f"Storage cleanup failed: {cleanup_error}"
                )

        # Direct database DELETE is intentionally
        # not attempted because admin permissions
        # prohibit it.
        #
        # If draw_id exists, the pending draw can
        # be removed through the secure deletion
        # workflow after investigating the failure.

        details = (
            f"Lottery result upload failed: {error}"
        )

        if draw_id:
            details += (
                f" | Pending Draw ID: {draw_id}. "
                "Use Admin Operations > "
                "Delete Pending Result for cleanup."
            )

        if cleanup_errors:
            details += (
                " | Cleanup issues: "
                + "; ".join(cleanup_errors)
            )

        raise RuntimeError(details) from error


def download_lottery_file(
    admin_client,
    storage_path,
):
    """
    Download a lottery result file from private
    Supabase Storage.
    """

    _validate_admin_client(admin_client)

    if not isinstance(storage_path, str):
        raise ValueError(
            "Storage path is required."
        )

    if (
        not storage_path.startswith("lottery-results/")
        or ".." in storage_path
        or "\\" in storage_path
    ):
        raise ValueError(
            "Invalid lottery result storage path."
        )

    file_bytes = (
        admin_client.storage
        .from_(BUCKET_NAME)
        .download(storage_path)
    )

    if not isinstance(file_bytes, bytes):
        raise RuntimeError(
            "Invalid file response from Storage."
        )

    return file_bytes
