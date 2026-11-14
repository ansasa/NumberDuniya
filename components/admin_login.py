
import streamlit as st
from supabase import create_client
from services.supabase_client import SUPABASE_URL, SUPABASE_KEY


def show_admin_login():
    st.subheader("🔐 NumberDuniya Admin Login")

    if st.session_state.get("admin_authenticated"):
        st.success("Admin session active!")
        return

    with st.form("admin_login_form"):
        email = st.text_input("Admin Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if not email or not password:
            st.warning("Please enter email and password.")
            return

        try:
            client = create_client(
                SUPABASE_URL,
                SUPABASE_KEY
            )

            response = client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if not response.user or not response.session:
                st.error("Invalid login.")
                return

            result = (
                client.table("admin_users")
                .select("user_id")
                .eq("user_id", response.user.id)
                .execute()
            )

            if result.data:
                st.session_state["admin_authenticated"] = True
                st.session_state["admin_client"] = client
                st.success("Admin login successful!")
                st.rerun()
            else:
                client.auth.sign_out()
                st.error("Access denied. Admin only.")

        except Exception:
            st.error("Login failed. Check your credentials.")
