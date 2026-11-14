
"""Admin-only, resumable deletion of pending lottery draws.

Requires database RPCs reserve_pending_lottery_deletion and
finalize_pending_lottery_deletion with appropriate authorization checks.
Storage and Postgres cannot be deleted in one atomic transaction.
"""

from uuid import UUID

from services.lottery_upload_service import BUCKET_NAME

STORAGE_PREFIX = "lottery-results/"


def _validate_storage_path(path):
    if not isinstance(path, str) or not path:
        raise ValueError(
            "Missing or invalid Storage path; deletion stopped."
        )

    if (
        not path.startswith(STORAGE_PREFIX)
        or path == STORAGE_PREFIX
        or path.startswith("/")
        or "\\" in path
        or any(
            segment in ("", ".", "..")
            for segment in path.split("/")
        )
    ):
        raise ValueError(f"Unsafe Storage path: {path!r}")

    return path


def _get_draw(client, draw_id):
    result = (
        client.table("lottery_draws")
        .select("draw_id, lottery_name, result_date, status")
        .eq("draw_id", draw_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError("Draw not found or not accessible.")

    return result.data[0]


def _get_storage_paths(client, draw_id):
    result = (
        client.table("lottery_result_uploads")
        .select("upload_id, storage_path")
        .eq("draw_id", draw_id)
        .execute()
    )

    paths = []

    for upload in result.data or []:
        path = _validate_storage_path(
            upload.get("storage_path")
        )

        if path not in paths:
            paths.append(path)

    return paths


def _assert_exclusive_paths(client, draw_id, paths):
    """Stop if a file path belongs to another draw."""

    for path in paths:
        result = (
            client.table("lottery_result_uploads")
            .select("draw_id")
            .eq("storage_path", path)
            .neq("draw_id", draw_id)
            .limit(1)
            .execute()
        )

        if result.data:
            raise RuntimeError(
                "Storage path is referenced by another draw: "
                f"{path!r}. Deletion stopped."
            )


def _storage_file_exists(storage, path):
    folder, filename = path.rsplit("/", 1)

    offset = 0
    limit = 100

    while True:
        records = storage.list(
            folder,
            {
                "limit": limit,
                "offset": offset,
            },
        )

        if not isinstance(records, list):
            raise RuntimeError(
                "Unexpected Storage listing response."
            )

        if any(
            isinstance(item, dict)
            and item.get("name") == filename
            for item in records
        ):
            return True

        if len(records) < limit:
            return False

        offset += limit


def _extract_removed_paths(response):
    if not isinstance(response, list):
        raise RuntimeError(
            "Unexpected Storage deletion response."
        )

    return {
        record["name"]
        for record in response
        if isinstance(record, dict)
        and isinstance(record.get("name"), str)
    }


def delete_pending_lottery_result(
    admin_client,
    draw_id,
):
    """
    Reserve pending draw, clean Storage,
    then finalize database deletion.

    Already-deleting draws can resume cleanup.
    """

    if admin_client is None:
        raise ValueError(
            "Authenticated admin client required."
        )

    valid_draw_id = str(UUID(str(draw_id)))

    auth_response = admin_client.auth.get_user()

    if not getattr(auth_response, "user", None):
        raise PermissionError(
            "Administrator login required."
        )

    draw = _get_draw(
        admin_client,
        valid_draw_id,
    )

    if draw.get("status") not in (
        "pending",
        "deleting",
    ):
        raise ValueError(
            "Only pending or already-reserved "
            "draws are eligible."
        )

    # Validate paths before reserving.
    paths = _get_storage_paths(
        admin_client,
        valid_draw_id,
    )

    _assert_exclusive_paths(
        admin_client,
        valid_draw_id,
        paths,
    )

    if draw["status"] == "pending":
        admin_client.rpc(
            "reserve_pending_lottery_deletion",
            {"p_draw_id": valid_draw_id},
        ).execute()

    try:
        reserved = _get_draw(
            admin_client,
            valid_draw_id,
        )

        if reserved.get("status") != "deleting":
            raise RuntimeError(
                "Draw is not in deleting status."
            )

        paths = _get_storage_paths(
            admin_client,
            valid_draw_id,
        )

        _assert_exclusive_paths(
            admin_client,
            valid_draw_id,
            paths,
        )

        storage = admin_client.storage.from_(
            BUCKET_NAME
        )

        removed_count = 0

        for path in paths:

            # Supports interrupted deletion recovery.
            if not _storage_file_exists(
                storage,
                path,
            ):
                continue

            response = storage.remove([path])

            if path not in _extract_removed_paths(
                response
            ):
                raise RuntimeError(
                    "Storage did not acknowledge "
                    f"deletion: {path}"
                )

            if _storage_file_exists(
                storage,
                path,
            ):
                raise RuntimeError(
                    f"Storage file still exists: {path}"
                )

            removed_count += 1

        # Recheck ownership before finalization.
        _assert_exclusive_paths(
            admin_client,
            valid_draw_id,
            paths,
        )

        admin_client.rpc(
            "finalize_pending_lottery_deletion",
            {"p_draw_id": valid_draw_id},
        ).execute()

        remaining = (
            admin_client.table("lottery_draws")
            .select("draw_id")
            .eq("draw_id", valid_draw_id)
            .limit(1)
            .execute()
        )

        if remaining.data:
            raise RuntimeError(
                "Database deletion could not be verified."
            )

        return {
            "success": True,
            "draw_id": valid_draw_id,
            "lottery_name": draw.get("lottery_name"),
            "result_date": draw.get("result_date"),
            "deleted_file_count": removed_count,
            "status": "deleted",
        }

    except Exception as error:
        raise RuntimeError(
            "Deletion incomplete. Draw may remain "
            "in 'deleting' status. Check the draw "
            "and Storage state before using "
            "'Resume Incomplete Deletion'. "
            f"Details: {error}"
        ) from error
