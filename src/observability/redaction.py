from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

_SENSITIVE_FRAGMENTS = {
    "password",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "customer_name",
    "account_number",
    "email",
    "phone",
    "passport",
    "kyc",
    "raw_prompt",
    "prompt_content",
    "completion_content",
}


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def sanitize(value: Any, *, depth: int = 0) -> Any:
    """Bound and redact telemetry values; never mutate the business object."""
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if is_sensitive_key(str(key)) else sanitize(item, depth=depth + 1)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, bytes):
        return f"[BYTES:{len(value)}]"
    if isinstance(value, str) and len(value) > 2048:
        return value[:2048] + "…[TRUNCATED]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:2048]


def stable_fingerprint(value: Any) -> str:
    """Non-reversible short fingerprint for loop detection; never a metric label."""
    safe = repr(sanitize(value)).encode("utf-8")
    return hashlib.sha256(safe).hexdigest()[:16]
