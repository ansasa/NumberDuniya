
import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

# Load local .env file, if available
load_dotenv()


def get_config(key):
    """Read local environment variables or Streamlit Cloud secrets."""
    value = os.getenv(key)

    if value:
        return value

    try:
        return st.secrets.get(key)
    except (FileNotFoundError, KeyError):
        return None


SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_KEY = get_config("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "Supabase credentials are missing. "
        "Configure .env locally or Streamlit Cloud secrets."
    )

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
