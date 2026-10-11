"""Small dependency-free signed bearer tokens for the enterprise API."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from cryptography.fernet import Fernet


def _load_secret():
    """Return a stable signing key across local uvicorn reloads."""
    configured = os.getenv("OPSAGENT_API_SECRET", "").strip()
    if configured:
        return configured
    secret_file = Path(
        os.getenv(
            "OPSAGENT_API_SECRET_FILE",
            str(Path(__file__).resolve().parents[1] / ".opsagent-api-secret"),
        )
    )
    try:
        existing = secret_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    generated = secrets.token_urlsafe(48)
    secret_file.write_text(generated, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return generated


_APPLICATION_SECRET = _load_secret()
_SECRET = _APPLICATION_SECRET.encode()
_FERNET = Fernet(base64.urlsafe_b64encode(hashlib.sha256(_SECRET).digest()))


def application_secret():
    """Shared stable secret for signed tokens and browser OAuth sessions."""
    return _APPLICATION_SECRET


def encrypt_secret(value):
    return _FERNET.encrypt(str(value).encode()).decode()


def decrypt_secret(value):
    return _FERNET.decrypt(str(value).encode()).decode()


def issue(user, lifetime_seconds=8 * 60 * 60):
    payload = {
        "sub": user["username"], "name": user["display_name"], "role": user["role"],
        "exp": int(time.time()) + lifetime_seconds,
    }
    if user.get("organization_id"):
        payload["org"] = user["organization_id"]
        payload["org_role"] = user.get("organization_role")
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_SECRET, body, hashlib.sha256).digest()
    return f"{body.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def verify(token):
    try:
        body_text, signature_text = token.split(".", 1)
        body = body_text.encode()
        supplied = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_SECRET, body, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        return payload if int(payload.get("exp", 0)) > int(time.time()) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
