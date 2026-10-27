import streamlit as st
import base64

from utils.user_store import (
    SESSION_TTL_SECONDS,
    authenticate,
    change_password,
    create_session_token,
)


_BROWSER_SESSION_BRIDGE = st.components.v2.component(
    "fusion_finance_browser_session",
    html="<div></div>",
    js="""
export default function (component) {
  const { data, setStateValue } = component
  const storageKey = "fusion_finance_session_v1"

  try {
    if (data?.clear) {
      window.localStorage.removeItem(storageKey)
      if (data.currentToken) setStateValue("token", "")
    } else {
      if (data?.tokenToStore) {
        window.localStorage.setItem(storageKey, data.tokenToStore)
      }
      const browserToken = window.localStorage.getItem(storageKey) || ""
      if (browserToken !== (data?.currentToken || "")) {
        setStateValue("token", browserToken)
      }
    }
    if (!data?.ready) setStateValue("ready", true)
  } catch (_) {
    if (!data?.ready) setStateValue("ready", true)
  }
}
""",
)


def mount_browser_session_bridge(token_to_store=None, clear=False):
    state = st.session_state.get("browser_auth_bridge", {})
    result = _BROWSER_SESSION_BRIDGE(
        key="browser_auth_bridge",
        data={
            "tokenToStore": token_to_store,
            "clear": clear,
            "currentToken": state.get("token", ""),
            "ready": state.get("ready", False),
        },
        default={"token": "", "ready": False},
        on_token_change=lambda: None,
        on_ready_change=lambda: None,
        height=1,
    )
    return result.token or "", bool(result.ready)


# ==========================================================
# Background Image and centered login page
# ==========================================================

def add_bg_from_local(image_file):
    with open(image_file, "rb") as image:
        encoded = base64.b64encode(image.read()).decode("ascii")

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image:
                linear-gradient(125deg, rgba(172, 62, 8, .56), rgba(8, 25, 50, .25)),
                url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}

        #MainMenu, footer, header {{ visibility: hidden; }}

        div[data-testid="stMainBlockContainer"] {{
            max-width: 100% !important;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 1.5rem 1rem !important;
        }}

        .st-key-login_card {{
            width: 100%;
            max-width: 720px;
            min-height: 640px;
            margin: 0 auto;
            box-sizing: border-box;
            padding: 2.5rem 3rem 2.25rem;
            border: 2px solid rgba(255,255,255,.96);
            border-top: 12px solid #F36F21;
            border-radius: 30px;
            background:
                linear-gradient(145deg, rgba(255,255,255,.96), rgba(250,250,252,.90));
            box-shadow:
                0 40px 100px rgba(5, 20, 42, .40),
                0 12px 30px rgba(200, 78, 17, .20),
                inset 0 1px 0 rgba(255,255,255,.96),
                inset 0 -1px 0 rgba(255,255,255,.35);
            backdrop-filter: blur(28px) saturate(155%);
            -webkit-backdrop-filter: blur(28px) saturate(155%);
        }}

        .st-key-login_card h1 {{
            color: #172B4D !important;
            font-size: 2.5rem;
            letter-spacing: -.03em;
            margin: 1rem 0 .35rem;
        }}

        .st-key-login_card [data-testid="stCaptionContainer"] {{
            color: #667085;
            font-size: 1rem;
        }}

        .st-key-login_card .stButton button {{
            min-height: 54px;
            border-radius: 12px;
            font-size: 1.05rem;
            font-weight: 700;
        }}

        .st-key-login_card .stButton button[kind="primary"] {{
            border: 1px solid rgba(255,255,255,.5) !important;
            background: linear-gradient(110deg, #F36F21, #E95420) !important;
            box-shadow: 0 9px 20px rgba(221, 83, 26, .28);
        }}

        .st-key-login_card .stButton button[kind="primary"]:hover {{
            box-shadow: 0 12px 26px rgba(221, 83, 26, .36);
            filter: brightness(1.04);
        }}

        .st-key-login_card .stButton button[kind="secondary"] {{
            color: #344054 !important;
            background: #FFFFFF !important;
            border: 1px solid #D0D5DD !important;
        }}

        .st-key-login_card [data-testid="stTextInput"] input {{
            min-height: 64px;
            border: 1px solid #E8EAF0;
            border-radius: 18px;
            background: linear-gradient(180deg, #FFFFFF, #FAFAFC);
            box-shadow: inset 0 2px 5px rgba(28, 39, 60, .04);
            font-size: 1.2rem;
        }}

        .st-key-login_card [data-testid="stTextInput"] label p {{
            font-size: 1.15rem;
            font-weight: 750;
            color: #344054;
        }}

        .st-key-login_card [data-testid="stForm"] {{
            background: transparent;
        }}

        .st-key-login_card [data-testid="stCheckbox"] label p {{
            font-size: 1.08rem;
            color: #28364A;
        }}

        .st-key-login_card [data-testid="stMarkdownContainer"] .login-method-pill {{
            display: inline-flex;
            align-items: center;
            gap: .55rem;
            padding: .65rem 1.2rem;
            margin: .65rem 0 .5rem;
            border-radius: 16px;
            color: #FFFFFF;
            background: linear-gradient(110deg, #F58235, #EE641F);
            box-shadow: 0 6px 16px rgba(221, 83, 26, .2);
            font-size: 1.08rem;
            font-weight: 700;
        }}

        .st-key-login_card [data-testid="stCheckbox"] {{
            padding-top: .2rem;
        }}

        .st-key-login_card [data-testid="stCheckbox"] label p {{
            font-size: .98rem;
        }}

        @media (max-width: 760px) {{
            .st-key-login_card {{
                min-height: auto;
                padding: 1.75rem 1.25rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==========================================================
# Login Page
# ==========================================================

def show_login():
    add_bg_from_local("assets/background.png")
    # Place the sign-in card in the right portion of the screen.
    spacer, right_panel = st.columns([1, 1.8], gap="large")

    with right_panel:
        with st.container(key="login_card"):
            st.image("assets/Fusion_Finance_Logo.png", width=175)

            if "auth_mode" not in st.session_state:
                st.session_state.auth_mode = "login"

            if st.session_state.auth_mode == "login":
                st.title(":material/lock: Login to Risk Management")
                st.caption("Sign in to the Fusion Finance Risk Management Portal.")
                st.markdown(
                    '<div class="login-method-pill">'
                    '<svg width="20" height="20" viewBox="0 0 24 24" '
                    'fill="currentColor" aria-hidden="true">'
                    '<path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-4.2 0-7.5 2.1-7.5 4.7V21h15v-2.3c0-2.6-3.3-4.7-7.5-4.7Z"/>'
                    '</svg><span>User ID</span></div>',
                    unsafe_allow_html=True,
                )

                with st.form("login_form", border=False):
                    username = st.text_input(
                        "User ID",
                        placeholder="Enter User ID",
                        key="login_username",
                        autocomplete="username",
                    )
                    password = st.text_input(
                        "Password",
                        placeholder="Enter Password",
                        type="password",
                        key="login_password",
                        autocomplete="current-password",
                    )
                    remember_me = st.checkbox(
                        "Remember me on this device",
                        key="login_remember",
                        value=True,
                    )
                    submitted = st.form_submit_button(
                        "Login",
                        type="primary",
                        width="stretch",
                    )

                if submitted:
                    is_valid, role = authenticate(username.strip(), password)
                    if is_valid:
                        ttl = 60 * 60 * 24 * 30 if remember_me else SESSION_TTL_SECONDS
                        token = create_session_token(username.strip(), ttl_seconds=ttl)
                        st.session_state.logged_in = True
                        st.session_state.username = username.strip()
                        st.session_state.user_role = role or "user"
                        st.session_state.auth_mode = "login"
                        st.session_state.active_auth_token = token
                        st.session_state.browser_token_to_store = token
                        st.rerun()
                    else:
                        st.error("Invalid user ID or password.")

                if st.button(
                    "Change Password",
                    type="secondary",
                    width="stretch",
                    key="login_change_password",
                ):
                    st.session_state.auth_mode = "change"
                    st.rerun()

            else:
                st.title("Change password")
                st.caption("Verify your current password before choosing a new one.")

                with st.form("change_pwd_form"):
                    cp_user = st.text_input("User ID", key="cp_user")
                    cp_current = st.text_input("Current Password", type="password", key="cp_current")
                    cp_new = st.text_input("New Password", type="password", key="cp_new")
                    cp_confirm = st.text_input("Confirm New Password", type="password", key="cp_confirm")
                    submitted = st.form_submit_button("Update Password", width="stretch")

                if submitted:
                    if not cp_user or not cp_current or not cp_new or not cp_confirm:
                        st.error("Please fill all fields.")
                    elif cp_new != cp_confirm:
                        st.error("New password and confirmation do not match.")
                    elif cp_new == cp_current:
                        st.error("New password must be different from the current password.")
                    elif not authenticate(cp_user, cp_current)[0]:
                        st.error("Current user ID or password is incorrect.")
                    else:
                        try:
                            change_password(cp_user, cp_current, cp_new)
                            st.success("Password changed successfully. Please sign in with your new password.")
                            st.session_state.auth_mode = "login"
                        except Exception as exc:
                            st.error(f"Unable to change password: {exc}")

                if st.button("Back to Login", type="secondary", width="stretch"):
                    st.session_state.auth_mode = "login"
                    st.rerun()

            st.caption("Fusion Finance | Risk Management")


# ==========================================================
# Change Password Panel - Logged In User
# ==========================================================

def show_change_password_panel():

    if not st.session_state.get("logged_in"):

        st.info(
            "Please login to change your password."
        )

        return

    # Current logged-in user
    username = st.session_state.get("username")

    st.title("Change Password")

    with st.form("user_change_pwd_form"):

        current_pwd = st.text_input(
            "Current Password",
            type="password"
        )

        new_pwd = st.text_input(
            "New Password",
            type="password"
        )

        confirm_pwd = st.text_input(
            "Confirm New Password",
            type="password"
        )

        submitted = st.form_submit_button(
            "Change Password"
        )

    if submitted:

        if not current_pwd or not new_pwd or not confirm_pwd:

            st.error(
                "Please fill all fields."
            )

        elif new_pwd != confirm_pwd:

            st.error(
                "New password and confirmation do not match."
            )

        elif new_pwd == current_pwd:

            st.error(
                "New password must be different from current password."
            )

        else:

            try:

                change_password(
                    username,
                    current_pwd,
                    new_pwd,
                    preserve_session_token=st.session_state.get(
                        "active_auth_token"
                    ),
                )

                st.success(
                    "Password changed successfully."
                )

            except Exception as exc:

                st.error(
                    f"Unable to change password: {exc}"
                )
