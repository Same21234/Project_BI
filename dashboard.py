import streamlit as st

from utils.report_registry import REPORTS
from utils.report_helpers import get_available_months
from utils.user_store import add_user, delete_session_token, get_users, set_password
from login import show_change_password_panel


# ==========================================================
# ADMIN - STAKEHOLDER MANAGEMENT
# ==========================================================

def _render_user_admin():

    if st.session_state.get("user_role") != "admin":
        st.error("Admin access is required for stakeholder management.")
        return

    st.markdown("### 👥 Stakeholder Management")

    st.info(
        "Create dashboard accounts or reset any stakeholder password here. "
        "Users can change their own password from Change Password."
    )

    users = get_users()

    # ======================================================
    # ADD NEW USER
    # ======================================================

    with st.expander(
        "Add new stakeholder user",
        expanded=False
    ):

        with st.form("create_stakeholder_user_form", border=False):
            new_username = st.text_input("User ID", key="new_user_username")
            new_fullname = st.text_input("User Name", key="new_user_name")
            new_password = st.text_input(
                "Initial Password", type="password", key="new_user_password"
            )
            new_password_confirm = st.text_input(
                "Confirm Password", type="password", key="new_user_password_confirm"
            )
            new_role = st.selectbox(
                "Role", ["user", "admin"], index=0, key="new_user_role"
            )
            create_submitted = st.form_submit_button(
                "Create User", width="stretch"
            )

        if create_submitted:
            new_username = new_username.strip()
            new_fullname = new_fullname.strip()

            if not new_username:

                st.error(
                    "User ID is required."
                )

            elif new_username in users:

                st.error(
                    "User ID already exists."
                )

            elif not new_password:

                st.error(
                    "Initial Password is required."
                )

            elif new_password != new_password_confirm:

                st.error(
                    "Password and confirmation do not match."
                )

            else:

                try:

                    add_user(
                        new_username,
                        new_password,
                        new_role,
                        name=new_fullname,
                    )

                    st.success(
                        f"User '{new_username}' created successfully."
                    )

                except Exception as exc:

                    st.error(
                        str(exc)
                    )

    with st.expander("Reset stakeholder password", expanded=False):
        users = get_users()

        def _user_option(username):
            user = users[username]
            name = user.get("name", "").strip()
            role = user.get("role", "user")
            label = f"{name} ({username})" if name else username
            return f"{label} · {role}"

        with st.form("reset_stakeholder_password_form", border=False):
            target_username = st.selectbox(
                "Select user",
                list(users),
                format_func=_user_option,
                key="reset_user_target",
            )
            reset_password = st.text_input(
                "Temporary password",
                type="password",
                key="reset_user_password",
            )
            reset_password_confirm = st.text_input(
                "Confirm temporary password",
                type="password",
                key="reset_user_password_confirm",
            )
            reset_submitted = st.form_submit_button(
                "Reset Password", width="stretch"
            )

        if reset_submitted:
            if not reset_password:
                st.error("Enter a temporary password.")
            elif reset_password != reset_password_confirm:
                st.error("Password and confirmation do not match.")
            else:
                current_username = st.session_state.get("username")
                preserve_token = (
                    st.session_state.get("active_auth_token")
                    if target_username == current_username
                    else None
                )
                try:
                    set_password(
                        target_username,
                        reset_password,
                        preserve_session_token=preserve_token,
                    )
                    st.success(
                        f"Password reset for '{target_username}'. "
                        "Their other active sessions have been signed out."
                    )
                except Exception as exc:
                    st.error(str(exc))

    # ======================================================
    # EXISTING USERS
    # ======================================================

    st.markdown("#### Existing Users")

    users = get_users()

    for username, details in users.items():

        display_name = details.get(
            "name",
            ""
        )

        role = details.get(
            "role",
            "user"
        )

        if display_name:

            st.write(
                f"- {username} ({role}) - {display_name}"
            )

        else:

            st.write(
                f"- {username} ({role})"
            )


# ==========================================================
# DASHBOARD
# ==========================================================

def show_dashboard():

    # ======================================================
    # SIDEBAR
    # ======================================================

    with st.sidebar:

        st.image(
            "assets/Fusion_Finance_Logo.png",
            use_container_width=True
        )

        st.markdown("---")

        # ==================================================
        # REPORT SELECTION
        # ==================================================

        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] [data-testid="stRadio"]
            [role="radiogroup"] label p {
                font-size: 16px !important;
                font-weight: 700 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        selected_report = st.radio(
            "📊 Reports",
            list(REPORTS.keys())
        )

        report_info = REPORTS[
            selected_report
        ]

        # ==================================================
        # MONTH SELECTION
        # ==================================================

        if report_info.get("uses_internal_filters"):
            selected_month = None
        else:
            months = get_available_months(
                report_info["view"]
            )

            def _fmt_month(m):
                try:
                    from datetime import datetime
                    return datetime.strptime(
                        str(m), "%Y-%m-%d"
                    ).strftime("%b-%y")
                except Exception:
                    return str(m)

            selected_month = st.selectbox(
                "Select Month",
                months,
                format_func=_fmt_month
            )

        st.markdown("---")

        # ==================================================
        # LOGGED-IN USER
        # ==================================================

        st.write(
            f"👤 {st.session_state.get('username', 'Admin')}"
        )

        # ==================================================
        # CHANGE PASSWORD
        # ==================================================

        if st.button(
            "Change Password",
            key="sidebar_change_password"
        ):

            st.session_state.show_change_password = True

            st.rerun()

        # ==================================================
        # ADMIN STAKEHOLDER MANAGEMENT
        # ==================================================

        if (
            st.session_state.get("user_role")
            == "admin"
        ):

            _render_user_admin()

        # ==================================================
        # LOGOUT
        # ==================================================

        if st.button(
            "🚪 Logout",
            use_container_width=True
        ):

            auth_token = st.session_state.get("active_auth_token")
            if auth_token:
                delete_session_token(auth_token)

            st.session_state.clear_browser_session = True
            st.session_state.pop("active_auth_token", None)
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.user_role = ""
            st.session_state.show_change_password = False

            st.rerun()

    # ======================================================
    # CHANGE PASSWORD PANEL
    # ======================================================

    if st.session_state.get(
        "show_change_password"
    ):

        st.session_state.show_change_password = False

        show_change_password_panel()

        return

    # ======================================================
    # LOAD REPORT
    # ======================================================

    report_info["function"](
        selected_month
    )
