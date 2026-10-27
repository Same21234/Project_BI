import streamlit as st

# ======================================================
# PAGE CONFIG (Always First Streamlit Command)
# ======================================================

st.set_page_config(
    page_title="Fusion Finance | Risk Management",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================================================
# IMPORTS
# ======================================================

from utils.helpers import load_css
from login import mount_browser_session_bridge, show_login
from dashboard import show_dashboard
from utils.user_store import get_users, validate_session_token

# ======================================================
# LOAD GLOBAL CSS
# ======================================================

load_css()

# ======================================================
# SESSION STATE
# ======================================================

# Initialize session state defaults
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

if "user_role" not in st.session_state:
    st.session_state.user_role = ""

token_to_store = st.session_state.pop("browser_token_to_store", None)
clear_browser_session = st.session_state.pop("clear_browser_session", False)
browser_token, bridge_ready = mount_browser_session_bridge(
    token_to_store=token_to_store,
    clear=clear_browser_session,
)

if not st.session_state.logged_in and browser_token and not clear_browser_session:
    restored_username = validate_session_token(browser_token)
    user = get_users().get(restored_username) if restored_username else None
    if user:
        st.session_state.logged_in = True
        st.session_state.username = restored_username
        st.session_state.user_role = user.get("role", "user")
        st.session_state.active_auth_token = browser_token
    else:
        st.session_state.clear_browser_session = True
        st.rerun()

# Enforce password-reset and logout revocation in already-open browser sessions.
if st.session_state.logged_in:
    active_token = st.session_state.get("active_auth_token")
    active_username = st.session_state.get("username")
    if active_token and validate_session_token(active_token) != active_username:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.user_role = ""
        st.session_state.pop("active_auth_token", None)
        st.session_state.clear_browser_session = True
        st.rerun()

if not bridge_ready and not st.session_state.logged_in:
    st.info("Restoring your sign-in session...")
    st.stop()


# ======================================================
# APPLICATION FLOW
# ======================================================

if st.session_state.logged_in:
    show_dashboard()
else:
    show_login()
