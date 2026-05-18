"""Session auth — HMAC-signed tokens, stored in httponly cookies.

No extra dependencies — uses stdlib hmac + secrets + json + base64.
"""
import hmac
import hashlib
import secrets
import json
import base64
import time
from pathlib import Path

_SECRET_FILE = Path.home() / ".kiro-proxy" / "portal_secret.key"

def _get_secret() -> bytes:
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes()
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    _SECRET_FILE.write_bytes(secret)
    return secret


def _sign(payload: dict, expires_in: int = 86400 * 7) -> str:
    """Create signed token. Returns base64url string."""
    payload = {**payload, "exp": int(time.time()) + expires_in}
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(_get_secret(), data, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{encoded}.{sig_b64}"


def _verify(token: str) -> dict | None:
    """Verify and decode a signed token. Returns payload or None."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        encoded, sig_b64 = parts
        # Restore padding
        data = base64.urlsafe_b64decode(encoded + "==")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        expected = hmac.new(_get_secret(), data, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(data)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_user_session(user_id: int, student_id: str) -> str:
    return _sign({"uid": user_id, "sid": student_id, "role": "user"})


def create_admin_session(username: str) -> str:
    return _sign({"username": username, "role": "admin"}, expires_in=86400)


def verify_user_session(token: str) -> dict | None:
    payload = _verify(token)
    if payload and payload.get("role") == "user":
        return payload
    return None


def verify_admin_session(token: str) -> dict | None:
    payload = _verify(token)
    if payload and payload.get("role") == "admin":
        return payload
    return None
