import os
import re

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


# ==========================================
# SUPABASE CLIENT
# ==========================================

def get_public_supabase_client():
    """Create a separate public client; never reuse an admin session."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase configuration is missing.")
    if not SUPABASE_KEY.startswith("sb_publishable_"):
        raise RuntimeError("A Supabase publishable key is required.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================
# SEARCH INPUT VALIDATION
# ==========================================

def validate_ticket_number(ticket_number):
    """Accept only four or five ASCII digits, preserving leading zeros."""
    if not isinstance(ticket_number, str):
        raise ValueError("Ticket number must be text.")
    ticket_number = ticket_number.strip()
    if not re.fullmatch(r"[0-9]{4,5}", ticket_number):
        raise ValueError("Enter a valid 4-digit or 5-digit lottery number.")
    return ticket_number


# ==========================================
# ORIGINAL SEARCH RPC (BACKWARD COMPATIBILITY)
# ==========================================

def search_winning_number(ticket_number):
    """Original capped search retained for other callers."""
    ticket_number = validate_ticket_number(ticket_number)
    client = get_public_supabase_client()
    response = client.rpc(
        "search_published_winning_number",
        {"p_winning_number": ticket_number},
    ).execute()
    return response.data or []


# ==========================================
# SERVER-SIDE PAGINATED SEARCH
# ==========================================

def search_winning_number_page(ticket_number, page=1, page_size=8):
    """Return only one page of published matches, with a total count.

    The PostgreSQL function performs filtering, ordering, and LIMIT/OFFSET.
    """
    ticket_number = validate_ticket_number(ticket_number)
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("Page must be a positive integer.")
    if (isinstance(page_size, bool) or not isinstance(page_size, int)
            or not 1 <= page_size <= 50):
        raise ValueError("Page size must be between 1 and 50.")

    client = get_public_supabase_client()
    response = client.rpc(
        "search_published_winning_number_page_v1",
        {
            "p_winning_number": ticket_number,
            "p_page": page,
            "p_page_size": page_size,
        },
    ).execute()
    records = response.data or []
    total_count = int(records[0].get("total_count") or 0) if records else 0
    # Do not expose the pagination metadata as a result-card field.
    cleaned = [
        {key: value for key, value in record.items() if key != "total_count"}
        for record in records
    ]
    return {"records": cleaned, "total_count": total_count}


# ==========================================
# DYNAMIC NUMBER STATISTICS
# ==========================================

def get_number_search_statistics(ticket_number):
    """Historical statistics calculated across all published draws."""
    ticket_number = validate_ticket_number(ticket_number)
    client = get_public_supabase_client()
    response = client.rpc(
        "get_number_search_statistics",
        {"p_winning_number": ticket_number},
    ).execute()
    data = response.data or []
    if not data:
        return {
            "total_published_draws": 0,
            "matching_draws": 0,
            "total_occurrences": 0,
            "historical_rate": 0.0,
        }
    statistics = data[0]
    return {
        "total_published_draws": int(statistics.get("total_published_draws") or 0),
        "matching_draws": int(statistics.get("matching_draws") or 0),
        "total_occurrences": int(statistics.get("total_occurrences") or 0),
        "historical_rate": float(statistics.get("historical_rate") or 0),
    }


# ==========================================
# PRIZE-WISE AND TIME-WISE BREAKDOWN
# ==========================================

def get_number_search_breakdown(ticket_number):
    """Existing prize-category and draw-session breakdown."""
    ticket_number = validate_ticket_number(ticket_number)
    client = get_public_supabase_client()
    response = client.rpc(
        "get_number_search_breakdown",
        {"p_winning_number": ticket_number},
    ).execute()
    data = response.data or []
    breakdown = []
    for item in data:
        breakdown.append({
            "draw_session": item.get("draw_session") or "N/A",
            "category_name": item.get("category_name") or "Unknown",
            "occurrences": int(item.get("occurrences") or 0),
        })
    return breakdown
