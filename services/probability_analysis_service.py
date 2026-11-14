"""NumberDuniya probability analysis service (Step 19.7)."""

import os
from dotenv import load_dotenv
from supabase import create_client
from services.frequency_analysis_service import get_winning_number_frequency

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_probability_distribution(scheme_name, category_name):
    """Legacy full-dataset helper retained for backwards compatibility."""
    frequency_data = get_winning_number_frequency(scheme_name, category_name)
    if not frequency_data:
        return []
    total_occurrences = sum(int(item["frequency"]) for item in frequency_data)
    if total_occurrences == 0:
        return []
    return [
        {
            "winning_number": str(item["winning_number"]),
            "frequency": int(item["frequency"]),
            "percentage": round(int(item["frequency"]) / total_occurrences * 100, 2),
        }
        for item in frequency_data
    ]


def get_winning_number_probability_page(scheme_name, category_name, page=1, page_size=12):
    """Fetch one page of globally computed historical shares from PostgreSQL."""
    if not isinstance(scheme_name, str) or not scheme_name.strip():
        raise ValueError("Lottery name is required.")
    if not isinstance(category_name, str) or not category_name.strip():
        raise ValueError("Prize category is required.")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000000:
        raise ValueError("Page must be an integer between 1 and 1000000.")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 50:
        raise ValueError("Page size must be an integer between 1 and 50.")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase configuration is missing.")
    if not SUPABASE_KEY.startswith("sb_publishable_"):
        raise RuntimeError("A Supabase publishable key is required.")

    response = create_client(SUPABASE_URL, SUPABASE_KEY).rpc(
        "get_winning_number_probability_page_v1",
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
        raise RuntimeError("Unexpected probability pagination response from Supabase.")
    if not isinstance(data.get("distribution"), list):
        raise RuntimeError("Missing distribution records in Supabase response.")
    return {
        "page": int(data.get("page", page)),
        "page_size": int(data.get("page_size", page_size)),
        "total_count": int(data.get("total_count", 0)),
        "total_pages": int(data.get("total_pages", 0)),
        "total_occurrences": int(data.get("total_occurrences", 0)),
        "distribution": data["distribution"],
    }
