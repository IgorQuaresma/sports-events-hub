"""RunSignup race search connector (https://runsignup.com/API).

The public race search (`GET https://runsignup.com/rest/races`) needs no credentials. If
RUNSIGNUP_API_KEY / RUNSIGNUP_API_SECRET are set they are sent as query credentials (never
stored). Coverage is strongest in North America — DACH has only a handful of races — so the
country list is configurable.

Config (all optional):
  {"countries": ["DE", "AT", "CH"],
   "months_ahead": 18,
   "per_page": 100,        # RunSignup allows up to 1000; stay polite
   "max_pages": 20,
   "base_url": "https://runsignup.com/rest"}

One listing call returns races *with* their events (`events=T`), so each race becomes its own
raw document without extra requests. Times are in the race's `timezone` (US/Eastern default).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.core.config import get_settings
from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.ingestion.fetcher import get_json
from app.ingestion.sport_mapping import RUNSIGNUP_EVENT_TYPES, sport_from_text
from app.schemas.candidate import (
    EventCandidate,
    LocationCandidate,
    PriceCandidate,
    RaceCandidate,
    RegistrationCandidate,
)

log = logging.getLogger("ingest.runsignup")

BASE = "https://runsignup.com/rest"
_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "CHF": "CHF", "EUR": "EUR", "USD": "USD"}
_DIST_RE = re.compile(
    r"(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>miles?|mi|kilometers?|km|k|meters?|m|yards?|y)\b",
    re.IGNORECASE,
)


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/New_York")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/New_York")


def _parse_us_date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v).strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _parse_us_dt(v: Any, tz: ZoneInfo) -> datetime | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def _distance_km(text: Any) -> float | None:
    if not text:
        return None
    m = _DIST_RE.search(str(text))
    if not m:
        return None
    n = float(m["n"].replace(",", "."))
    u = m["u"].lower()
    if u.startswith("mi"):
        return round(n * 1.609344, 3)
    if u in ("m", "meter", "meters"):
        return n / 1000
    if u.startswith("y"):
        return round(n * 0.0009144, 3)
    return n


def _distances(sport: str, km: float | None) -> dict[str, float]:
    if km is None:
        return {}
    if sport == "cycling":
        return {"bike_km": km}
    if sport == "swimming":
        return {"swim_m": km * 1000}
    if sport == "triathlon":
        return {}  # a single number is not meaningful for multisport
    return {"run_km": km}


def _price(fee: Any) -> tuple[float, str] | None:
    if not fee:
        return None
    s = str(fee).strip()
    currency = next((c for sym, c in _CURRENCY.items() if sym in s), "USD")
    num = re.search(r"\d+(?:[.,]\d{1,2})?", s.replace(",", ""))
    if not num:
        return None
    return float(num.group(0)), currency


def _registration(
    periods: list[dict], race_open: bool, url: str | None, tz: ZoneInfo
) -> RegistrationCandidate | None:
    now = datetime.now(UTC)
    prices: list[PriceCandidate] = []
    windows: list[tuple[datetime | None, datetime | None]] = []
    for p in periods or []:
        opens = _parse_us_dt(p.get("registration_opens"), tz)
        closes = _parse_us_dt(p.get("registration_closes"), tz)
        windows.append((opens, closes))
        price = _price(p.get("race_fee"))
        if price:
            prices.append(
                PriceCandidate(
                    label="Entry fee",
                    amount=price[0],
                    currency=price[1],
                    valid_from=opens,
                    valid_until=closes,
                )
            )
    if not windows and not race_open:
        return None
    opens_at = min((o for o, _ in windows if o), default=None)
    closes_at = max((c for _, c in windows if c), default=None)
    # the race-level flag is authoritative; periods only explain *why* it is not open
    if race_open:
        state = "open"
    elif any(o and o > now for o, _ in windows):
        state = "not_open"
    elif closes_at and closes_at < now:
        state = "closed"
    else:
        state = "unknown"
    return RegistrationCandidate(
        url=url,
        opens_at=opens_at,
        closes_at=closes_at,
        state=state,
        prices=prices,
        platform="runsignup",
    )


def _plain_text(html: str | None, limit: int = 1200) -> str | None:
    if not html:
        return None
    text = HTMLParser(html).text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else (text or None)


def candidate_from_race(race: dict, source_url: str) -> EventCandidate | None:
    name = race.get("name")
    start = _parse_us_date(race.get("next_date"))
    if not name or not start:
        return None
    tz = _tz(race.get("timezone"))
    events = [e for e in race.get("events") or [] if isinstance(e, dict)]
    typed = [(e, RUNSIGNUP_EVENT_TYPES.get(str(e.get("event_type")), None)) for e in events]
    sports = Counter(s for _, s in typed if s)
    sport = sports.most_common(1)[0][0] if sports else sport_from_text(name)
    if sport is None:
        return None  # virtual runs, expos, clinics, ...
    reg_url = race.get("url")
    race_open = str(race.get("is_registration_open", "F")).upper() == "T"
    races: list[RaceCandidate] = []
    for ev, ev_sport in typed:
        if ev_sport != sport or not ev.get("name"):
            continue
        races.append(
            RaceCandidate(
                name=str(ev["name"])[:200],
                start_time=_parse_us_dt(ev.get("start_time"), tz),
                distances=_distances(sport, _distance_km(ev.get("distance"))),
                relay="relay" in str(ev["name"]).lower(),
                registration=_registration(
                    ev.get("registration_periods") or [], race_open, reg_url, tz
                ),
            )
        )
    addr = race.get("address") or {}
    website = race.get("external_race_url")
    return EventCandidate(
        name=str(name)[:200],
        sport_slug=sport,
        start_date=start,
        end_date=_parse_us_date(race.get("next_end_date")),
        location=LocationCandidate(
            street=addr.get("street"),
            postal_code=addr.get("zipcode"),
            city=addr.get("city"),
            region=addr.get("state"),
            country=addr.get("country_code"),
        ),
        website=website if str(website or "").startswith("http") else reg_url,
        registration_url=reg_url,
        registration_platform="runsignup",
        races=races,
        description=_plain_text(race.get("description")),
        language="en",
        source_url=reg_url or source_url,
        external_id=f"runsignup:{race.get('race_id')}",
    )


class RunSignupConnector:
    key = "runsignup"

    def __init__(self, config: dict[str, Any]) -> None:
        s = get_settings()
        self.api_key = s.secret("runsignup_api_key")
        self.api_secret = s.secret("runsignup_api_secret")
        self.base_url = str(config.get("base_url", BASE)).rstrip("/")
        self.countries = [c.upper() for c in config.get("countries", ["DE", "AT", "CH"])]
        self.months_ahead = int(config.get("months_ahead", 18))
        self.per_page = min(int(config.get("per_page", 100)), 1000)
        self.max_pages = int(config.get("max_pages", 20))

    def _secret_params(self) -> dict[str, str] | None:
        if self.api_key and self.api_secret:
            return {"api_key": self.api_key, "api_secret": self.api_secret}
        return None

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        today = date.today()
        end = today + timedelta(days=30 * self.months_ahead)
        for country in self.countries:
            for page in range(1, self.max_pages + 1):
                params = {
                    "format": "json",
                    "country": country,
                    "start_date": today.isoformat(),
                    "end_date": end.isoformat(),
                    "events": "T",
                    "results_per_page": self.per_page,
                    "page": page,
                    "sort": "date ASC",
                }
                _raw, body = await get_json(
                    fetcher,
                    f"{self.base_url}/races?{urlencode(params)}",
                    headers={"Accept": "application/json"},
                    secret_params=self._secret_params(),
                )
                if isinstance(body, dict) and body.get("error"):
                    raise RuntimeError(f"RunSignup error: {body.get('error')}")
                rows = (body or {}).get("races") or []
                for row in rows:
                    race = row.get("race") if isinstance(row, dict) else None
                    if not isinstance(race, dict) or race.get("is_private_race") == "T":
                        continue
                    yield DiscoveredItem(
                        url=f"{self.base_url}/race/{race.get('race_id')}",
                        external_id=str(race.get("race_id")),
                        hint={"race": race},
                    )
                if len(rows) < self.per_page:
                    break

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        return RawDocument(
            url=item.url,
            body=json.dumps(item.hint["race"], sort_keys=True).encode(),
            fetched_at=datetime.now(UTC),
            http_status=200,
            content_type="application/json",
            external_id=item.external_id,
        )

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        cand = candidate_from_race(json.loads(raw.body), raw.url)
        return [ParseResult(candidate=cand, method="api", confidence=0.9)] if cand else []
