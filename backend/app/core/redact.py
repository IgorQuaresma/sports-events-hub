"""Keep credentials out of URLs that we log, store or show (provenance, errors, admin views)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SENSITIVE_KEYS = re.compile(
    r"(api[_-]?key|apikey|api[_-]?secret|secret|token|password|passwd|auth|signature|sig|key)$",
    re.IGNORECASE,
)
REDACTED = "REDACTED"


def redact_url(url: str) -> str:
    """Replace credential-looking query parameters and userinfo with a placeholder."""
    try:
        parts = urlparse(url)
    except ValueError:
        return url
    netloc = parts.netloc
    if "@" in netloc:
        netloc = f"{REDACTED}@{netloc.rsplit('@', 1)[1]}"
    if not parts.query and netloc == parts.netloc:
        return url
    query = urlencode(
        [
            (k, REDACTED if SENSITIVE_KEYS.search(k) else v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
        ],
        safe=",:",
    )
    return urlunparse(parts._replace(netloc=netloc, query=query))


def redact_text(text: str, secrets: list[str | None]) -> str:
    """Remove known secret values from free text such as exception messages."""
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, REDACTED)
    return text


def redact_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Shallow copy of a source config with secret-looking keys masked (for admin output)."""
    return {
        k: (REDACTED if SENSITIVE_KEYS.search(k) and v else v) for k, v in (config or {}).items()
    }
