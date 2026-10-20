"""World Triathlon Events API connector (https://developers.triathlon.org).

Works out of the box: without WORLD_TRIATHLON_API_KEY it reads the keyless public mirror
(`https://triathlon.org/tri-api/v1`, the API behind triathlon.org); with a key it uses the
official `https://api.triathlon.org/v1` and sends the key in the `apikey` header.

Config (all optional):
  {"countries": ["DE", "AT", "CH"],      # ISO alpha-2 filter applied client-side
   "region_id": 10,                      # 10 = Europe (narrows the listing server-side)
   "months_ahead": 18,                   # listing window from today
   "per_page": 100,
   "fetch_programs": true,               # one extra call per event for its races ("programs")
   "max_events": 500,
   "max_pages": 50,
   "base_url": "..."}                    # override the endpoint (tests, proxies)

Endpoints used:
  GET {base}/events?region_id=&start_date=&end_date=&per_page=&page=&order=asc
  GET {base}/events/{event_id}          (detail incl. `programs` = races)
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from dateutil import parser as dtparser

from app.core.config import get_settings
from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.ingestion.connectors.jsonld import distances_from_text
from app.ingestion.fetcher import get_json
from app.schemas.candidate import EventCandidate, LocationCandidate, RaceCandidate

log = logging.getLogger("ingest.world_triathlon")

OFFICIAL_BASE = "https://api.triathlon.org/v1"
PUBLIC_MIRROR = "https://triathlon.org/tri-api/v1"

# World Triathlon "specification" names → our taxonomy
SPEC_TO_DISCIPLINE = {
    "super sprint": "super-sprint",
    "sprint": "sprint",
    "standard": "olympic",
    "olympic": "olympic",
    "middle distance": "middle",
    "middle": "middle",
    "long distance": "long",
    "long": "long",
    "relay": "relay",
    "mixed relay": "relay",
    "team relay": "relay",
}
STATUS_MAP = {
    "scheduled": "scheduled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "postponed": "postponed",
    "completed": "finished",
    "finished": "finished",
}


def _discipline_from_specs(specs: list[dict], name: str) -> str | None:
    names = [str(s.get("cat_name", "")).lower() for s in specs or []]
    for n in names:
        if n in SPEC_TO_DISCIPLINE:
            return SPEC_TO_DISCIPLINE[n]
    low = name.lower()
    for key, disc in SPEC_TO_DISCIPLINE.items():
        if re.search(rf"\b{re.escape(key)}\b", low):
            return disc
    return None


def _program_distances(prog: dict) -> dict[str, float]:
    """Programs may carry a `prog_distances` list ({segment, distance}); else parse the name."""
    out: dict[str, float] = {}
    for seg in prog.get("prog_distances") or []:
        if not isinstance(seg, dict):
            continue
        label = str(seg.get("segment", "")).lower()
        try:
            dist = float(seg.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        if not dist:
            continue
        if "swim" in label:
            out["swim_m"] = dist if dist > 50 else dist * 1000
        elif "bike" in label or "cycle" in label:
            out["bike_km"] = dist if dist < 400 else dist / 1000
        elif "run" in label:
            out["run_km"] = dist if dist < 100 else dist / 1000
    if not out:
        text = f"{prog.get('prog_name', '')} {prog.get('prog_distance_category', '')}"
        out = distances_from_text(text, "triathlon")
    return out


def _parse_dt(d: Any, t: Any = None) -> datetime | None:
    if not d:
        return None
    try:
        if t:
            return dtparser.parse(f"{d} {t}")
        return dtparser.parse(str(d))
    except (ValueError, TypeError):
        return None


def _http_url(v: Any) -> str | None:
    return v if isinstance(v, str) and v.startswith(("http://", "https://")) else None


def candidate_from_event(
    ev: dict, programs: list[dict] | None, source_url: str
) -> EventCandidate | None:
    title = ev.get("event_title")
    start = ev.get("event_date")
    if not title or not start:
        return None
    try:
        start_date = date.fromisoformat(str(start)[:10])
    except ValueError:
        return None
    end_raw = ev.get("event_finish_date")
    try:
        end_date = date.fromisoformat(str(end_raw)[:10]) if end_raw else None
    except ValueError:
        end_date = None
    venue = ev.get("event_venue") or None
    specs = ev.get("event_specifications") or []
    races: list[RaceCandidate] = []
    for prog in programs or []:
        if not isinstance(prog, dict) or not prog.get("prog_name"):
            continue
        if prog.get("is_race") is False:  # coaches' meetings, briefings, ...
            continue
        pname = str(prog["prog_name"])
        races.append(
            RaceCandidate(
                name=pname,
                discipline_slug=_discipline_from_specs(specs, pname),
                start_time=_parse_dt(prog.get("prog_date"), prog.get("prog_time")),
                distances=_program_distances(prog),
                relay="relay" in pname.lower(),
                team=bool(prog.get("team")),
                attributes={"draft_legal": True} if "elite" in pname.lower() else {},
            )
        )
    if not races:
        races.append(
            RaceCandidate(
                name=title,
                discipline_slug=_discipline_from_specs(specs, title),
                distances=distances_from_text(title, "triathlon"),
                relay=any("relay" in str(s.get("cat_name", "")).lower() for s in specs),
            )
        )
    website = _http_url(ev.get("event_website"))
    listing = _http_url(ev.get("event_listing"))
    # the API repeats categories; keep the first occurrence of each, in order
    cats = ", ".join(
        dict.fromkeys(
            str(c.get("cat_name")) for c in ev.get("event_categories") or [] if c.get("cat_name")
        )
    )
    spec_names = ", ".join(
        dict.fromkeys(str(s.get("cat_name")) for s in specs if s.get("cat_name"))
    )
    desc = " · ".join(x for x in [cats, spec_names] if x) or None
    try:
        lat = float(ev["event_latitude"]) if ev.get("event_latitude") is not None else None
        lon = float(ev["event_longitude"]) if ev.get("event_longitude") is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    return EventCandidate(
        name=title,
        sport_slug="triathlon",
        start_date=start_date,
        end_date=end_date if end_date and end_date >= start_date else None,
        location=LocationCandidate(
            text=venue,
            city=venue.split(",")[0].strip() if venue else None,
            country=ev.get("event_country_isoa2") or None,
            lat=lat,
            lon=lon,
        ),
        website=website or listing,
        registration_url=website,
        registration_platform="organizer" if website else None,
        races=races,
        description=f"World Triathlon listing: {desc}" if desc else None,
        language="en",
        source_url=listing or source_url,
        external_id=str(ev.get("event_id")),
        status=STATUS_MAP.get(str(ev.get("event_status", "")).lower(), "scheduled"),
    )


class WorldTriathlonConnector:
    key = "world_triathlon"

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = get_settings().secret("world_triathlon_api_key")
        default_base = OFFICIAL_BASE if self.api_key else PUBLIC_MIRROR
        self.base_url = str(config.get("base_url", default_base)).rstrip("/")
        self.countries = {c.upper() for c in config.get("countries", ["DE", "AT", "CH"])}
        self.region_id = config.get("region_id", 10)
        self.months_ahead = int(config.get("months_ahead", 18))
        self.per_page = int(config.get("per_page", 100))
        self.fetch_programs = bool(config.get("fetch_programs", True))
        self.max_events = int(config.get("max_events", 500))
        self.max_pages = int(config.get("max_pages", 50))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key and self.base_url == OFFICIAL_BASE:
            headers["apikey"] = self.api_key
        return headers

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        if self.base_url == OFFICIAL_BASE and not self.api_key:
            raise RuntimeError("the official World Triathlon API needs WORLD_TRIATHLON_API_KEY")
        today = date.today()
        end = today + timedelta(days=30 * self.months_ahead)
        params: dict[str, Any] = {
            "start_date": today.isoformat(),
            "end_date": end.isoformat(),
            "per_page": self.per_page,
            "order": "asc",
            "page": 1,
        }
        if self.region_id:
            params["region_id"] = self.region_id
        yielded = 0
        while True:
            _raw, body = await get_json(
                fetcher, f"{self.base_url}/events?{urlencode(params)}", headers=self._headers()
            )
            for ev in body.get("data") or []:
                if not isinstance(ev, dict):
                    continue
                # the mirror may ignore the date filter: re-check client-side
                if str(ev.get("event_date", ""))[:10] < params["start_date"]:
                    continue
                if (
                    self.countries
                    and str(ev.get("event_country_isoa2", "")).upper() not in self.countries
                ):
                    continue
                yield DiscoveredItem(
                    url=f"{self.base_url}/events/{ev.get('event_id')}",
                    external_id=str(ev.get("event_id")),
                    hint={"event": ev},
                )
                yielded += 1
                if yielded >= self.max_events:
                    return
            last = int(body.get("last_page") or 1)
            if params["page"] >= min(last, self.max_pages):
                return
            params["page"] += 1

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        if self.fetch_programs:
            raw, _ = await get_json(fetcher, item.url, headers=self._headers())
            raw.external_id = item.external_id
            return raw
        body = json.dumps({"data": item.hint["event"]}).encode()
        return RawDocument(
            url=item.url,
            body=body,
            fetched_at=datetime.now(UTC),
            http_status=200,
            content_type="application/json",
            external_id=item.external_id,
        )

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        body = json.loads(raw.body)
        ev = body.get("data") if isinstance(body.get("data"), dict) else body
        if not isinstance(ev, dict):
            return []
        programs = ev.get("programs") if isinstance(ev.get("programs"), list) else None
        cand = candidate_from_event(ev, programs, raw.url)
        if cand is None:
            return []
        return [ParseResult(candidate=cand, method="api", confidence=0.95)]
