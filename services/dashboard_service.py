
def get_dashboard_metrics(admin_client):
    """
    Fetch live dashboard metrics from Supabase.

    Uses the authenticated admin client.
    """

    if admin_client is None:
        raise ValueError("Admin client is required.")

    # Count uploaded result files
    uploaded_response = (
        admin_client.table("lottery_result_uploads")
        .select(
            "upload_id",
            count="exact",
            head=True
        )
        .execute()
    )

    # Count pending lottery draws
    pending_response = (
        admin_client.table("lottery_draws")
        .select(
            "draw_id",
            count="exact",
            head=True
        )
        .eq("status", "pending")
        .execute()
    )

    # Count published lottery draws
    published_response = (
        admin_client.table("lottery_draws")
        .select(
            "draw_id",
            count="exact",
            head=True
        )
        .eq("status", "published")
        .execute()
    )

    return {
        "uploaded_results": uploaded_response.count or 0,
        "pending_verification": pending_response.count or 0,
        "published_results": published_response.count or 0
    }


def get_uploaded_results(admin_client):
    """
    Fetch uploaded lottery results with draw details.

    Includes state and lottery scheme metadata
    for accurate Gemini extraction validation.

    Requires an authenticated admin client.
    """

    if admin_client is None:
        raise ValueError("Admin client is required.")

    response = (
        admin_client.table("lottery_result_uploads")
        .select(
            "upload_id, draw_id, file_name, file_type, storage_path, "
            "upload_status, uploaded_at, "
            "lottery_draws("
            "state_name, lottery_name, scheme_name, "
            "result_date, draw_time, status"
            ")"
        )
        .order("uploaded_at", desc=True)
        .limit(100)
        .execute()
    )

    return response.data or []
