"""Security helpers: URL/config redaction, click hashing, rate limiting, settings guards,
and the fetcher keeping credentials out of stored URLs."""

from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.redact import REDACTED, redact_config, redact_text, redact_url
from app.core.security import SlidingWindowLimiter, pseudonymous_client_hash
from app.ingestion import fetcher as fetcher_mod
from app.ingestion.fetcher import FetchError, HttpFetcher
from app.ingestion.sport_mapping import sport_from_text


def test_redact_url():
    u = redact_url("https://api.example.org/v2/events.json?apikey=abc123&size=10&api_secret=x")
    assert "abc123" not in u and "size=10" in u and u.count(REDACTED) == 2
    assert redact_url("https://user:pw@example.org/x") == f"https://{REDACTED}@example.org/x"
    assert redact_url("https://example.org/a?b=c") == "https://example.org/a?b=c"


def test_redact_config_and_text():
    assert redact_config({"api_key": "s3cr3t", "countries": ["DE"]}) == {
        "api_key": REDACTED, "countries": ["DE"]}
    assert redact_text("401 for key s3cr3t-value", ["s3cr3t-value", None]) == f"401 for key {REDACTED}"


def test_click_hash_is_salted_and_rotates_daily():
    a = pseudonymous_client_hash("203.0.113.7", "UA", date(2027, 1, 1))
    b = pseudonymous_client_hash("203.0.113.7", "UA", date(2027, 1, 2))
    assert a != b and len(a) == 64
    import hashlib

    assert a != hashlib.sha256(b"203.0.113.7|UA").hexdigest()


def test_sliding_window_limiter():
    lim = SlidingWindowLimiter(limit=2, window_s=60)
    assert lim.allow("ip") and lim.allow("ip") and not lim.allow("ip") and lim.allow("other")


def test_default_secrets_rejected_in_prod():
    with pytest.raises(ValidationError, match="SERVICE_TOKEN"):
        Settings(environment="prod", _env_file=None)
    ok = Settings(environment="prod", service_token="x" * 32, click_hash_salt="y" * 32,
                  _env_file=None)
    assert ok.is_prod


@pytest.mark.parametrize(
    ("text", "sport"),
    [("Trail-Halbmarathon Zugspitze", "trail-running"), ("HYROX Wien", "hyrox"),
     ("Allgäu Triathlon", "triathlon"), ("Spartan Race Oberndorf", "ocr"),
     ("Radmarathon Tannheimer Tal", "cycling"), ("Silvesterlauf Trier", "running"),
     ("Radio Konzert", None)],
)
def test_sport_from_text(text, sport):
    assert sport_from_text(text) == sport


async def test_fetcher_keeps_secret_params_out_of_document(monkeypatch):
    seen: list[str] = []

    def app(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, json={"ok": True})

    async def _safe(_url):
        return None

    monkeypatch.setattr(fetcher_mod, "assert_safe_url", _safe)
    f = HttpFetcher(min_delay_s=0)
    f._client = httpx.AsyncClient(transport=httpx.MockTransport(app))
    raw = await f.get("https://api.example.org/events?size=1", secret_params={"apikey": "TOPSECRET"})
    await f.aclose()
    assert any("apikey=TOPSECRET" in u for u in seen)  # sent upstream ...
    assert "TOPSECRET" not in raw.url  # ... but never stored


async def test_fetcher_errors_do_not_leak_secrets(monkeypatch):
    def app(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {request.url}")

    async def _safe(_url):
        return None

    monkeypatch.setattr(fetcher_mod, "assert_safe_url", _safe)
    f = HttpFetcher(respect_robots=False, min_delay_s=0)
    f._client = httpx.AsyncClient(transport=httpx.MockTransport(app))
    with pytest.raises(FetchError) as exc:
        await f.get("https://api.example.org/e", secret_params={"apikey": "TOPSECRET"})
    await f.aclose()
    assert "TOPSECRET" not in str(exc.value)


async def test_fetcher_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def app(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={})

    async def _safe(_url):
        return None

    monkeypatch.setattr(fetcher_mod, "assert_safe_url", _safe)
    f = HttpFetcher(respect_robots=False, min_delay_s=0)
    f._client = httpx.AsyncClient(transport=httpx.MockTransport(app))
    raw = await f.get("https://api.example.org/e")
    await f.aclose()
    assert raw.http_status == 200 and calls["n"] == 2
