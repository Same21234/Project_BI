import hashlib
import json
from pathlib import Path
import uuid
import time


# ==========================================================
# USER DATABASE
# ==========================================================

USER_DB_PATH = Path("users.json")

DEFAULT_USERS = {
    "admin": {
        "password_hash": hashlib.sha256(
            "admin".encode("utf-8")
        ).hexdigest(),
        "role": "admin",
        "name": "Administrator"
    }
}


# ==========================================================
# SESSION DATABASE
# ==========================================================

SESSIONS_DB_PATH = Path("sessions.json")

SESSION_TTL_SECONDS = 60 * 60 * 24  # 1 day


# ==========================================================
# USER DATABASE FUNCTIONS
# ==========================================================

def _ensure_user_db():

    if not USER_DB_PATH.exists():
        save_users(DEFAULT_USERS)


def load_users():

    _ensure_user_db()

    with USER_DB_PATH.open(
        "r",
        encoding="utf-8"
    ) as handle:

        users = json.load(handle)

    # Ensure existing users have a name field
    changed = False

    for username, details in users.items():

        if "name" not in details:

            details["name"] = ""

            changed = True

    if changed:
        save_users(users)

    return users


def save_users(users):

    with USER_DB_PATH.open(
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            users,
            handle,
            indent=2
        )


# ==========================================================
# PASSWORD FUNCTIONS
# ==========================================================

def hash_password(password):

    return hashlib.sha256(
        str(password).encode("utf-8")
    ).hexdigest()


def authenticate(username, password):

    users = load_users()

    user = users.get(username)

    if not user:
        return False, None

    valid = (
        user.get("password_hash")
        == hash_password(password)
    )

    if valid:
        return True, user.get("role", "user")

    return False, None


# ==========================================================
# ADD USER
# ==========================================================

def add_user(
    username,
    password,
    role="user",
    name=""
):

    username = str(username).strip()

    if not username:
        raise ValueError(
            "User ID cannot be empty."
        )

    if not password:
        raise ValueError(
            "Password cannot be empty."
        )

    users = load_users()

    if username in users:

        raise ValueError(
            f"User '{username}' already exists."
        )

    users[username] = {
        "password_hash": hash_password(password),
        "role": role,
        "name": str(name).strip()
    }

    save_users(users)

    return True


# ==========================================================
# GET USERS
# ==========================================================

def get_users():

    return load_users()


# ==========================================================
# CHANGE OWN PASSWORD
# ==========================================================

def change_password(
    username,
    old_password,
    new_password,
    preserve_session_token=None,
):

    users = load_users()

    user = users.get(username)

    if not user:

        raise ValueError(
            f"User '{username}' does not exist."
        )

    if (
        user.get("password_hash")
        != hash_password(old_password)
    ):

        raise ValueError(
            "Current password is incorrect."
        )

    if not new_password:

        raise ValueError(
            "New password cannot be empty."
        )

    if old_password == new_password:

        raise ValueError(
            "New password must be different from current password."
        )

    users[username]["password_hash"] = (
        hash_password(new_password)
    )

    save_users(users)
    _revoke_user_sessions(username, preserve_session_token)

    return True


# ==========================================================
# ADMIN PASSWORD RESET
# ==========================================================

def set_password(
    username,
    new_password,
    preserve_session_token=None,
):

    users = load_users()

    if username not in users:

        raise ValueError(
            f"User '{username}' does not exist."
        )

    if not new_password:

        raise ValueError(
            "New password cannot be empty."
        )

    users[username]["password_hash"] = (
        hash_password(new_password)
    )

    save_users(users)

    # A reset signs the user out everywhere, except an optional current
    # session when the account owner changes their own password.
    _revoke_user_sessions(username, preserve_session_token)

    return True


# ==========================================================
# UPDATE USER DETAILS
# ==========================================================

def update_user(
    username,
    new_username=None,
    name=None,
    role=None
):
    """
    Update User ID, Name and/or Role.

    Existing password is preserved.
    """

    users = load_users()

    if username not in users:

        raise ValueError(
            f"User '{username}' does not exist."
        )

    current_data = users[username]

    # ------------------------------------------------------
    # Determine new username
    # ------------------------------------------------------

    if new_username is None:

        final_username = username

    else:

        final_username = str(
            new_username
        ).strip()

        if not final_username:

            raise ValueError(
                "New User ID cannot be empty."
            )

        # Prevent duplicate User ID
        if (
            final_username != username
            and final_username in users
        ):

            raise ValueError(
                f"User ID '{final_username}' already exists."
            )

    # ------------------------------------------------------
    # Preserve existing data
    # ------------------------------------------------------

    updated_data = dict(current_data)

    # ------------------------------------------------------
    # Update Name
    # ------------------------------------------------------

    if name is not None:

        updated_data["name"] = str(
            name
        ).strip()

    elif "name" not in updated_data:

        updated_data["name"] = ""

    # ------------------------------------------------------
    # Update Role
    # ------------------------------------------------------

    if role is not None:

        if role not in ["user", "admin"]:

            raise ValueError(
                "Role must be either 'user' or 'admin'."
            )

        updated_data["role"] = role

    # ------------------------------------------------------
    # Rename User ID if required
    # ------------------------------------------------------

    if final_username != username:

        del users[username]

        users[final_username] = updated_data

    else:

        users[username] = updated_data

    save_users(users)

    return True


# ==========================================================
# RENAME USER ID ONLY
# ==========================================================

def rename_user(
    username,
    new_username
):

    return update_user(
        username=username,
        new_username=new_username
    )


# ==========================================================
# UPDATE USER NAME ONLY
# ==========================================================

def update_user_name(
    username,
    name
):

    return update_user(
        username=username,
        name=name
    )


# ==========================================================
# UPDATE USER ROLE ONLY
# ==========================================================

def update_user_role(
    username,
    role
):

    return update_user(
        username=username,
        role=role
    )


# ==========================================================
# SESSION TOKEN MANAGEMENT
# ==========================================================

def _ensure_sessions_db():

    if not SESSIONS_DB_PATH.exists():

        save_sessions({})


def load_sessions():

    _ensure_sessions_db()

    with SESSIONS_DB_PATH.open(
        "r",
        encoding="utf-8"
    ) as handle:

        return json.load(handle)


def save_sessions(sessions):

    with SESSIONS_DB_PATH.open(
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            sessions,
            handle,
            indent=2
        )


def _revoke_user_sessions(username, preserve_session_token=None):
    sessions = load_sessions()
    stale_tokens = [
        token
        for token, details in sessions.items()
        if details.get("username") == username
        and token != preserve_session_token
    ]

    for token in stale_tokens:
        del sessions[token]

    if stale_tokens:
        save_sessions(sessions)


def create_session_token(
    username,
    ttl_seconds=SESSION_TTL_SECONDS
):

    sessions = load_sessions()

    token = uuid.uuid4().hex

    expiry = (
        int(time.time())
        + int(ttl_seconds)
    )

    sessions[token] = {
        "username": username,
        "expiry": expiry
    }

    save_sessions(sessions)

    return token


def validate_session_token(token):

    sessions = load_sessions()

    if token not in sessions:

        return None

    entry = sessions[token]

    if int(time.time()) > int(
        entry.get("expiry", 0)
    ):

        try:

            del sessions[token]

            save_sessions(sessions)

        except Exception:
            pass

        return None

    return entry.get("username")


def delete_session_token(token):

    sessions = load_sessions()

    if token in sessions:

        del sessions[token]

        save_sessions(sessions)

        return True

    return False
