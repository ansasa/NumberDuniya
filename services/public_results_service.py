import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _public_client():
    """Use a separate publishable-key client, never an admin session."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase configuration is missing.")
    if not SUPABASE_KEY.startswith("sb_publishable_"):
        raise RuntimeError("Public results require a Supabase publishable key.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_public_lottery_results(limit=10):
    """Original published-only RPC with nested prizes; retained for compatibility."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("Limit must be an integer.")
    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")
    response = _public_client().rpc(
        "get_public_lottery_results_v2", {"p_limit": limit}
    ).execute()
    return response.data or []


def get_published_draws_page(page=1, page_size=4):
    """Fetch one database-paginated page of published draw metadata.

    The count comes from COUNT(*) OVER() in the SQL RPC. An empty out-of-range
    page has no total_count; the UI queries page one first to avoid this case.
    """
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("Page must be a positive integer.")
    if (isinstance(page_size, bool) or not isinstance(page_size, int)
            or not 1 <= page_size <= 20):
        raise ValueError("Page size must be between 1 and 20.")
    response = _public_client().rpc(
        "get_published_draws_page_v1",
        {"p_page": page, "p_page_size": page_size},
    ).execute()
    data = response.data or []
    count = int(data[0].get("total_count") or 0) if data else 0
    return {
        "records": [{k: v for k, v in item.items() if k != "total_count"}
                    for item in data],
        "total_count": count,
    }


def get_published_prize_numbers_page(draw_id, category_name, page=1, page_size=9, search=""):
    """Return a published draw's prize numbers, filtered and paged in PostgreSQL."""
    if not isinstance(draw_id, str) or not draw_id.strip():
        raise ValueError("Draw ID is required.")
    if not isinstance(category_name, str) or not category_name.strip():
        raise ValueError("Prize category is required.")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000000:
        raise ValueError("Page must be between 1 and 1000000.")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 50:
        raise ValueError("Page size must be between 1 and 50.")
    if not isinstance(search, str) or len(search) > 100:
        raise ValueError("Search must be text of at most 100 characters.")
    response = _public_client().rpc(
        "get_published_prize_numbers_page_v1",
        {"p_draw_id": draw_id, "p_category_name": category_name,
         "p_page": page, "p_page_size": page_size, "p_search": search},
    ).execute()
    data = response.data
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected prize pagination response.")
    return {
        "winning_numbers": [str(n) for n in (data.get("winning_numbers") or [])],
        "total_count": int(data.get("total_count") or 0),
        "total_pages": int(data.get("total_pages") or 0),
        "page": int(data.get("page") or page),
    }
