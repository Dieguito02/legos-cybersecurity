from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

from backend.core.config import settings


def _sign(value: str) -> str:
    digest = hmac.new(settings.secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_session_token(username: str) -> str:
    payload = f"{username}:{os.urandom(16).hex()}"
    signature = _sign(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def verify_session_token(token: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, nonce, signature = raw.rsplit(":", 2)
        payload = f"{username}:{nonce}"
        expected = _sign(payload)
        if hmac.compare_digest(expected, signature):
            return username
    except Exception:
        return None
    return None


def validate_credentials(username: str, password: str) -> bool:
    return hmac.compare_digest(username or "", settings.app_username) and hmac.compare_digest(
        password or "", settings.app_password
    )
