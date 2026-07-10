import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pyotp
import qrcode

from app.core.config import settings

STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "auth_store.json"
ISSUER = "Jobyro"
SUPER_ADMIN_EMAIL = "admin@jobyro.local"
SUPER_ADMIN_PASSWORD = "Admin@12345"


def load_store() -> dict[str, Any]:
    if not STORE_PATH.exists():
        store = {"users": {}, "temp_passwords": []}
        save_store(store)
    else:
        store = json.loads(STORE_PATH.read_text(encoding="utf-8"))

    if SUPER_ADMIN_EMAIL not in store["users"]:
        store["users"][SUPER_ADMIN_EMAIL] = create_user_record(
            name="Super Admin",
            email=SUPER_ADMIN_EMAIL,
            password=SUPER_ADMIN_PASSWORD,
            role="super_admin",
            totp_confirmed=False,
        )
        save_store(store)
    return store


def save_store(store: dict[str, Any]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def create_user_record(name: str, email: str, password: str, role: str, totp_confirmed: bool) -> dict[str, Any]:
    secret = pyotp.random_base32()
    salt = secrets.token_hex(16)
    return {
        "name": name,
        "email": email.lower(),
        "role": role,
        "password_hash": hash_password(password, salt),
        "salt": salt,
        "totp_secret": secret,
        "totp_confirmed": totp_confirmed,
        "failed_attempts": 0,
        "locked": False,
        "temp_password_hash": "",
        "temp_password_salt": "",
        "created_at": now_iso(),
    }


def register_user(name: str, email: str, password: str) -> dict[str, str]:
    store = load_store()
    email_key = email.lower()
    if email_key in store["users"]:
        raise ValueError("An account already exists for this email.")

    user = create_user_record(name=name, email=email_key, password=password, role="user", totp_confirmed=False)
    store["users"][email_key] = user
    save_store(store)
    return build_totp_setup(user)


def setup_totp(email: str, password: str) -> dict[str, str]:
    store = load_store()
    user = get_user(store, email)
    if not verify_password(password, user["salt"], user["password_hash"]):
        raise PermissionError("Invalid password.")
    return build_totp_setup(user)


def build_totp_setup(user: dict[str, Any]) -> dict[str, str]:
    uri = pyotp.TOTP(user["totp_secret"]).provisioning_uri(name=user["email"], issuer_name=ISSUER)
    image = qrcode.make(uri)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"email": user["email"], "otp_uri": uri, "qr_data_url": data_url}


def confirm_totp(email: str, code: str) -> None:
    store = load_store()
    user = get_user(store, email)
    if not verify_totp(user, code):
        raise ValueError("Invalid authenticator code.")
    user["totp_confirmed"] = True
    save_store(store)


def login_user(email: str, password: str, code: str) -> dict[str, Any]:
    store = load_store()
    user = get_user(store, email)

    if user.get("locked"):
        raise PermissionError("Account is locked. Use reset password.")
    if not user.get("totp_confirmed"):
        raise PermissionError("Authenticator setup is required before login.")

    if not verify_password(password, user["salt"], user["password_hash"]):
        user["failed_attempts"] = int(user.get("failed_attempts", 0)) + 1
        if user["failed_attempts"] >= 3:
            user["locked"] = True
            issue_temp_password(store, user, reason="three_failed_password_attempts")
        save_store(store)
        raise PermissionError("Invalid password.")

    if not verify_totp(user, code):
        raise PermissionError("Invalid authenticator code.")

    user["failed_attempts"] = 0
    save_store(store)
    return {"token": create_token(user), "user": public_user(user)}


def forgot_password(email: str, code: str) -> None:
    store = load_store()
    user = get_user(store, email)
    if not verify_totp(user, code):
        raise PermissionError("Invalid authenticator code.")
    user["locked"] = True
    issue_temp_password(store, user, reason="forgot_password")
    save_store(store)


def reset_password(email: str, temporary_password: str, code: str, new_password: str) -> None:
    store = load_store()
    user = get_user(store, email)
    if not verify_totp(user, code):
        raise PermissionError("Invalid authenticator code.")
    if not user.get("temp_password_hash") or not verify_password(
        temporary_password, user["temp_password_salt"], user["temp_password_hash"]
    ):
        raise PermissionError("Invalid temporary password.")

    salt = secrets.token_hex(16)
    user["salt"] = salt
    user["password_hash"] = hash_password(new_password, salt)
    user["failed_attempts"] = 0
    user["locked"] = False
    user["temp_password_hash"] = ""
    user["temp_password_salt"] = ""
    save_store(store)


def issue_temp_password(store: dict[str, Any], user: dict[str, Any], reason: str) -> str:
    temp_password = "Temp-" + secrets.token_urlsafe(8)
    salt = secrets.token_hex(16)
    user["temp_password_salt"] = salt
    user["temp_password_hash"] = hash_password(temp_password, salt)
    store["temp_passwords"].append(
        {
            "email": user["email"],
            "name": user["name"],
            "temporary_password": temp_password,
            "reason": reason,
            "created_at": now_iso(),
        }
    )
    return temp_password


def get_temp_passwords(token: str) -> list[dict[str, Any]]:
    store = load_store()
    user = user_from_token(token)
    if user["role"] != "super_admin":
        raise PermissionError("Super admin access required.")
    return list(reversed(store.get("temp_passwords", [])))


def user_from_token(token: str) -> dict[str, Any]:
    payload = verify_token(token)
    store = load_store()
    user = get_user(store, payload["email"])
    return public_user(user)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {"name": user["name"], "email": user["email"], "role": user["role"]}


def get_user(store: dict[str, Any], email: str) -> dict[str, Any]:
    user = store["users"].get(email.lower())
    if not user:
        raise KeyError("Account not found.")
    return user


def verify_totp(user: dict[str, Any], code: str) -> bool:
    return pyotp.TOTP(user["totp_secret"]).verify(code, valid_window=1)


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return base64.b64encode(digest).decode("ascii")


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


def create_token(user: dict[str, Any]) -> str:
    payload = {
        "email": user["email"],
        "role": user["role"],
        "exp": (datetime.now(timezone.utc) + timedelta(hours=8)).timestamp(),
    }
    payload_raw = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    signature = sign(payload_raw)
    return f"{payload_raw}.{signature}"


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload_raw, signature = token.split(".", 1)
    except ValueError as exc:
        raise PermissionError("Invalid token.") from exc
    if not hmac.compare_digest(sign(payload_raw), signature):
        raise PermissionError("Invalid token.")
    payload = json.loads(base64.urlsafe_b64decode(payload_raw.encode("ascii")).decode("utf-8"))
    if float(payload["exp"]) < datetime.now(timezone.utc).timestamp():
        raise PermissionError("Token expired.")
    return payload


def sign(value: str) -> str:
    return hmac.new(settings.jwt_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
