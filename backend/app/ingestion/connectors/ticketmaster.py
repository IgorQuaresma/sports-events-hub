"""Ticketmaster Discovery API v2 connector (https://developer.ticketmaster.com).

Requires TICKETMASTER_API_KEY (free; 5000 calls/day, 5 req/s). The key travels as the
`apikey` query parameter, so it is passed as a *secret param* and never stored.

Ticketmaster mostly sells spectator tickets, but it also lists participation events
(HYROX, city runs, fitness races). We search per keyword and keep only events whose
name/classification maps onto our sport taxonomy.

Config (all optional):
  {"countries": ["DE", "AT", "CH"],
   "keywords": ["hyrox", "marathon", "triathlon", "lauf", "trail", "obstacle"],
   "months_ahead": 12,
   "per_page": 100,              # max 200; Ticketmaster caps size*page below 1000
   "locale": "*"}
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from dateutil import parser as dtparser

from app.core.config import get_settings
from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.ingestion.fetcher import get_json
from app.ingestion.sport_mapping import sport_from_text
from app.schemas.candidate import (
    EventCandidate,
    LocationCandidate,
    PriceCandidate,
    RaceCandidate,
    RegistrationCandidate,
)

log = logging.getLogger("ingest.ticketmaster")

BASE = "https://app.ticketmaster.com/discovery/v2"
DEFAULT_KEYWORDS = ["hyrox", "marathon", "triathlon", "lauf", "trail", "obstacle"]
# segments that are never participation sports events ("Run-DMC" is a concert)
NON_SPORT_SEGMENTS = {"music", "arts & theatre", "film"}
_STATE = {"onsale": "open", "offsale": "closed", "rescheduled": "open", "postponed": "unknown"}
_STATUS = {"cancelled": "cancelled", "canceled": "cancelled", "postponed": "postponed"}


def _dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return dtparser.isoparse(str(v))
    except (ValueError, TypeError):
        return None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _classification_text(ev: dict) -> str:
    parts: list[str] = []
    for c in ev.get("classifications") or []:
        for level in ("segment", "genre", "subGenre", "type", "subType"):
            name = (c.get(level) or {}).get("name")
            if name and name != "Undefined":
                parts.append(str(name))
    return " ".join(parts)


def candidate_from_event(ev: dict) -> EventCandidate | None:
    name = ev.get("name")
    start = ev.get("dates", {}).get("start", {})
    start_date = _date(start.get("localDate"))
    url = ev.get("url")
    if not name or not start_date or not str(url or "").startswith("https://"):
        return None
    classifications = ev.get("classifications") or []
    segments = {str((c.get("segment") or {}).get("name", "")).lower() for c in classifications}
    if segments & NON_SPORT_SEGMENTS:
        return None
    sport = sport_from_text(name, _classification_text(ev), ev.get("info"))
    if sport is None:
        return None  # a concert that happens to contain "run" etc.

    venues = (ev.get("_embedded") or {}).get("venues") or [{}]
    v = venues[0] or {}
    loc = v.get("location") or {}
    status_code = str((ev.get("dates", {}).get("status") or {}).get("code", "")).lower()
    sales = (ev.get("sales") or {}).get("public") or {}
    prices = [
        PriceCandidate(
            label=str(p.get("type") or "Ticket").title(),
            amount=float(p["min"]),
            currency=str(p.get("currency") or "EUR").upper(),
        )
        for p in ev.get("priceRanges") or []
        if isinstance(p, dict) and _float(p.get("min")) is not None
    ]
    registration = RegistrationCandidate(
        url=url,
        opens_at=_dt(sales.get("startDateTime")),
        closes_at=_dt(sales.get("endDateTime")),
        state=_STATE.get(status_code, "unknown"),
        prices=prices,
        platform="ticketmaster",
    )
    end_date = _date((ev.get("dates", {}).get("end") or {}).get("localDate"))
    promoter = (ev.get("promoter") or {}).get("name")
    return EventCandidate(
        name=str(name)[:200],
        sport_slug=sport,
        start_date=start_date,
        end_date=end_date if end_date and end_date >= start_date else None,
        location=LocationCandidate(
            name=v.get("name"),
            street=(v.get("address") or {}).get("line1"),
            postal_code=v.get("postalCode"),
            city=(v.get("city") or {}).get("name"),
            region=(v.get("state") or {}).get("name"),
            country=(v.get("country") or {}).get("countryCode"),
            lat=_float(loc.get("latitude")),
            lon=_float(loc.get("longitude")),
        ),
        organizer_name=promoter,
        website=url,
        registration_url=url,
        registration_platform="ticketmaster",
        races=[
            RaceCandidate(
                name=str(name)[:200],
                start_time=_dt(start.get("dateTime")),
                registration=registration,
            )
        ],
        description=(ev.get("info") or ev.get("pleaseNote") or None),
        language="de",
        source_url=url,
        external_id=f"ticketmaster:{ev.get('id')}",
        status=_STATUS.get(status_code, "scheduled"),
    )


class TicketmasterConnector:
    key = "ticketmaster"

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = get_settings().secret("ticketmaster_api_key")
        self.base_url = str(config.get("base_url", BASE)).rstrip("/")
        self.countries = [c.upper() for c in config.get("countries", ["DE", "AT", "CH"])]
        self.keywords: list[str] = list(config.get("keywords", DEFAULT_KEYWORDS))
        self.months_ahead = int(config.get("months_ahead", 12))
        self.per_page = min(int(config.get("per_page", 100)), 200)
        self.locale = str(config.get("locale", "*"))

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        if not self.api_key:
            raise RuntimeError("ticketmaster connector needs TICKETMASTER_API_KEY")
        now = datetime.now(UTC).replace(microsecond=0)
        end = now + timedelta(days=30 * self.months_ahead)
        seen: set[str] = set()
        max_page = max(0, (1000 // self.per_page) - 1)  # deep-paging cap: size*page < 1000
        for country in self.countries:
            for kw in self.keywords:
                page = 0
                while page <= max_page:
                    params = {
                        "countryCode": country,
                        "keyword": kw,
                        "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "size": self.per_page,
                        "page": page,
                        "sort": "date,asc",
                        "locale": self.locale,
                    }
                    _raw, body = await get_json(
                        fetcher,
                        f"{self.base_url}/events.json?{urlencode(params)}",
                        secret_params={"apikey": self.api_key},
                    )
                    events = ((body or {}).get("_embedded") or {}).get("events") or []
                    for ev in events:
                        eid = str(ev.get("id"))
                        if eid in seen:
                            continue
                        seen.add(eid)
                        yield DiscoveredItem(
                            url=f"{self.base_url}/events/{eid}.json",
                            external_id=eid,
                            hint={"event": ev},
                        )
                    total_pages = int(((body or {}).get("page") or {}).get("totalPages") or 0)
                    page += 1
                    if page >= total_pages:
                        break

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        # the search result already carries every field we use: no per-event call
        return RawDocument(
            url=item.url,
            body=json.dumps(item.hint["event"], sort_keys=True).encode(),
            fetched_at=datetime.now(UTC),
            http_status=200,
            content_type="application/json",
            external_id=item.external_id,
        )

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        cand = candidate_from_event(json.loads(raw.body))
        return [ParseResult(candidate=cand, method="api", confidence=0.85)] if cand else []
