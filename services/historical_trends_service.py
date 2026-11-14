import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _get_public_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase configuration is missing.")
    if not SUPABASE_KEY.startswith("sb_publishable_"):
        raise RuntimeError("A Supabase publishable key is required.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required.")
    return value.strip()


def _validate_page(page, page_size):
    if type(page) is not int or not 1 <= page <= 1000000:
        raise ValueError("Page must be an integer between 1 and 1000000.")
    if type(page_size) is not int or not 1 <= page_size <= 50:
        raise ValueError("Page size must be an integer between 1 and 50.")


def _rpc_json(name, parameters):
    response = _get_public_client().rpc(name, parameters).execute()
    data = response.data
    # Supabase may wrap a scalar JSON response in a one-element list.
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response from {name}.")
    return data


def get_historical_draws_page(scheme_name, category_name, *, page=1, page_size=5):
    """Get published draw summaries, paginated by PostgreSQL."""
    scheme_name = _require_text(scheme_name, "Lottery scheme")
    category_name = _require_text(category_name, "Prize category")
    _validate_page(page, page_size)
    data = _rpc_json("get_historical_draws_page_v1", {
        "p_scheme_name": scheme_name,
        "p_category_name": category_name,
        "p_page": page,
        "p_page_size": page_size,
    })
    for field in ("draws", "total_draws", "total_numbers", "total_pages"):
        if field not in data:
            raise RuntimeError(f"Historical draws response missing {field}.")
    return data


def get_historical_draw_numbers_page(draw_id, category_name, *, page=1, page_size=9):
    """Get winning-number strings for one published draw and category."""
    draw_id = _require_text(draw_id, "Draw ID")
    category_name = _require_text(category_name, "Prize category")
    _validate_page(page, page_size)
    data = _rpc_json("get_historical_draw_numbers_page_v1", {
        "p_draw_id": draw_id,
        "p_category_name": category_name,
        "p_page": page,
        "p_page_size": page_size,
    })
    for field in ("winning_numbers", "total_count", "total_pages"):
        if field not in data:
            raise RuntimeError(f"Historical numbers response missing {field}.")
    return data


def get_lottery_historical_trends(scheme_name, category_name):
    """Legacy full-history RPC retained for backward compatibility."""
    scheme_name = _require_text(scheme_name, "Lottery scheme")
    category_name = _require_text(category_name, "Prize category")
    response = _get_public_client().rpc("get_lottery_historical_trends", {
        "p_scheme_name": scheme_name,
        "p_category_name": category_name,
    }).execute()
    return response.data or []
