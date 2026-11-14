import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase configuration is missing.")
    if not SUPABASE_KEY.startswith("sb_publishable_"):
        raise RuntimeError("A Supabase publishable key is required.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_winning_number_frequency(scheme_name, category_name):
    """Existing full-frequency RPC retained for compatibility."""
    if not isinstance(scheme_name, str) or not scheme_name.strip():
        raise ValueError("Lottery scheme is required.")
    if not isinstance(category_name, str) or not category_name.strip():
        raise ValueError("Prize category is required.")
    response = _get_client().rpc(
        "get_winning_number_frequency",
        {"p_scheme_name": scheme_name, "p_category_name": category_name},
    ).execute()
    return response.data or []


def get_winning_number_frequency_page(scheme_name, category_name, page=1, page_size=12):
    """Aggregate across published draws in PostgreSQL, return only one page."""
    if not isinstance(scheme_name, str) or not scheme_name.strip():
        raise ValueError("Lottery scheme is required.")
    if not isinstance(category_name, str) or not category_name.strip():
        raise ValueError("Prize category is required.")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000000:
        raise ValueError("Page must be an integer between 1 and 1000000.")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 50:
        raise ValueError("Page size must be an integer between 1 and 50.")

    response = _get_client().rpc(
        "get_winning_number_frequency_page_v1",
        {
            "p_scheme_name": scheme_name,
            "p_category_name": category_name,
            "p_page": page,
            "p_page_size": page_size,
        },
    ).execute()
    data = response.data
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected frequency pagination response from Supabase.")
    frequencies = data.get("frequencies")
    if not isinstance(frequencies, list):
        raise RuntimeError("Missing frequency records in Supabase response.")
    return {
        "page": int(data.get("page", page)),
        "page_size": int(data.get("page_size", page_size)),
        "total_count": int(data.get("total_count", 0)),
        "total_pages": int(data.get("total_pages", 0)),
        "total_occurrences": int(data.get("total_occurrences", 0)),
        "frequencies": frequencies,
    }
