"""Minimal auth for the MVP: a service token for admin/ingest endpoints, plus small helpers.

User accounts (JWT, OAuth, passkeys) are planned for phase 3; see docs/IMPLEMENTATION_PLAN.md §9.
"""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings


async def require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {get_settings().service_token.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def pseudonymous_client_hash(client_ip: str, user_agent: str, day: date | None = None) -> str:
    """Salted, daily-rotating hash: counts unique clients per day without storing IPs.

    The secret salt prevents brute-forcing the small IPv4 space back to an address, and mixing
    in the date makes hashes unlinkable across days (DSGVO data minimisation).
    """
    salt = get_settings().click_hash_salt.get_secret_value()
    day = day or date.today()
    raw = f"{salt}|{day.isoformat()}|{client_ip}|{user_agent}".encode()
    return hashlib.sha256(raw).hexdigest()


class SlidingWindowLimiter:
    """In-memory per-key rate limiter (single process). Use Redis when running >1 replica."""

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under a key-spraying client
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v})
        return True


_parse_limiter: SlidingWindowLimiter | None = None


async def limit_parse_requests(request: Request) -> None:
    """Dependency guarding the NL parser (it may call a paid LLM)."""
    global _parse_limiter
    if _parse_limiter is None:
        _parse_limiter = SlidingWindowLimiter(get_settings().parse_rate_limit_per_minute)
    key = request.client.host if request.client else "unknown"
    if not _parse_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests, try again in a minute",
            headers={"Retry-After": "60"},
        )
