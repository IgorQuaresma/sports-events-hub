"""Polite, SSRF-hardened HTTP fetcher.

- only http/https; hostnames resolved and checked against private/loopback/link-local ranges
  before every connection, including each redirect hop
- robots.txt respected (cached per host), descriptive User-Agent, per-host minimum delay
- bounded retries with backoff on 429/5xx, honouring `Retry-After`
- body size and time limits
- credentials passed as `secret_params` never appear in stored URLs or error messages
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings
from app.core.redact import redact_text, redact_url
from app.ingestion.base import Fetcher, RawDocument

log = logging.getLogger("ingest.fetcher")

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_S = 60.0


class FetchError(Exception):
    pass


class UnsafeURL(FetchError):
    pass


class RobotsDisallowed(FetchError):
    pass


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL(f"scheme not allowed: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("missing host")
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeURL(f"host not allowed: {host}")
    try:
        infos = await asyncio.get_running_loop().run_in_executor(
            None, lambda: socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        )
    except socket.gaierror as e:
        raise UnsafeURL(f"cannot resolve {host}") from e
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise UnsafeURL(f"{host} resolves to non-public address {ip}")


def _with_params(url: str, params: dict[str, str] | None) -> str:
    if not params:
        return url
    sep = "&" if urlparse(url).query else "?"
    return f"{url}{sep}{urlencode(params)}"


def _retry_after_s(resp: httpx.Response, attempt: int) -> float:
    header = resp.headers.get("retry-after")
    if header:
        try:
            return min(float(header), MAX_RETRY_AFTER_S)
        except ValueError:
            try:
                delta = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
                return min(max(delta, 0.0), MAX_RETRY_AFTER_S)
            except (TypeError, ValueError):
                pass
    return min(2.0 ** (attempt + 1), MAX_RETRY_AFTER_S)


class HttpFetcher:
    def __init__(self, *, respect_robots: bool = True, min_delay_s: float | None = None) -> None:
        s = get_settings()
        self.user_agent = s.fetcher_user_agent
        self.timeout = s.fetch_timeout_s
        self.max_bytes = s.fetch_max_bytes
        self.min_delay = s.fetch_min_delay_s if min_delay_s is None else min_delay_s
        self.max_retries = s.fetch_max_retries
        self.respect_robots = respect_robots
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        headers = {"User-Agent": self.user_agent, "Accept-Language": "de,en;q=0.8"}
        if s.contact_email:
            headers["From"] = s.contact_email
        self._client = httpx.AsyncClient(
            headers=headers, timeout=self.timeout, follow_redirects=False
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.min_delay - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()

    async def _read_limited(self, resp: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > self.max_bytes:
                raise FetchError(f"body exceeds {self.max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    async def _raw_get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        await assert_safe_url(url)
        host = urlparse(url).netloc
        await self._throttle(host)
        req = self._client.build_request("GET", url, headers=headers)
        resp = await self._client.send(req, stream=True)
        try:
            body = await self._read_limited(resp)
        finally:
            await resp.aclose()
        resp._content = body  # noqa: SLF001 — keep the limited body on the response
        return resp

    async def _get_with_retries(self, url: str, headers: dict[str, str] | None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            resp = await self._raw_get(url, headers)
            if resp.status_code not in RETRY_STATUSES or attempt == self.max_retries:
                return resp
            delay = _retry_after_s(resp, attempt)
            log.warning(
                "HTTP %s from %s, retrying in %.1fs", resp.status_code, redact_url(url), delay
            )
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                resp = await self._raw_get(urljoin(base, "/robots.txt"))
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp = None  # no robots → allowed
            except (FetchError, httpx.HTTPError):
                rp = None
            self._robots[base] = rp
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        secret_params: dict[str, str] | None = None,
        check_robots: bool = True,
    ) -> RawDocument:
        if check_robots and self.respect_robots and not await self._robots_allowed(url):
            raise RobotsDisallowed(redact_url(url))
        secrets = list((secret_params or {}).values()) + list((headers or {}).values())
        current = url
        for _hop in range(5):
            try:
                resp = await self._get_with_retries(_with_params(current, secret_params), headers)
            except httpx.HTTPError as e:
                msg = redact_text(f"{redact_url(current)}: {type(e).__name__}: {e}", secrets)
                raise FetchError(msg) from None
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                # credentials are only sent to the host they were meant for
                nxt = urljoin(current, resp.headers["location"])
                if urlparse(nxt).netloc != urlparse(current).netloc:
                    secret_params, headers = None, None
                current = nxt
                continue
            return RawDocument(
                url=redact_url(current),
                body=resp.content,
                fetched_at=datetime.now(UTC),
                http_status=resp.status_code,
                content_type=resp.headers.get("content-type"),
            )
        raise FetchError(f"too many redirects from {redact_url(url)}")


async def get_json(fetcher: Fetcher, url: str, **kwargs: Any) -> tuple[RawDocument, Any]:
    """Fetch and decode JSON, turning HTTP errors into FetchError with a useful message."""
    raw = await fetcher.get(url, **kwargs)
    if raw.http_status is not None and raw.http_status >= 400:
        raise FetchError(f"{raw.url}: HTTP {raw.http_status}")
    try:
        return raw, json.loads(raw.body)
    except ValueError as e:
        raise FetchError(f"{raw.url}: invalid JSON ({e})") from None
