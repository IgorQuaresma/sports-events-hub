"""iCal feed connector (club / federation calendars).

Config: {"url": "https://.../calendar.ics", "sport_slug": "running", "country": "DE"}
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from icalendar import Calendar

from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.ingestion.connectors.jsonld import distances_from_text
from app.schemas.candidate import EventCandidate, LocationCandidate, RaceCandidate


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    d = v.dt if hasattr(v, "dt") else v
    return d.date() if isinstance(d, datetime) else d


class ICalConnector:
    key = "ical"

    def __init__(self, config: dict[str, Any]) -> None:
        self.url = config["url"]
        self.sport = config.get("sport_slug", "running")
        self.country = config.get("country")

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        yield DiscoveredItem(url=self.url)

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        return await fetcher.get(item.url)

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        cal = Calendar.from_ical(raw.body)
        out: list[ParseResult] = []
        for comp in cal.walk("VEVENT"):
            name = str(comp.get("SUMMARY", "")).strip()
            start = _as_date(comp.get("DTSTART"))
            if not name or not start:
                continue
            location = str(comp.get("LOCATION", "")).strip() or None
            city = location.split(",")[0].strip() if location else None
            url = str(comp.get("URL", "")).strip() or None
            desc = str(comp.get("DESCRIPTION", "")).strip() or None
            m = re.search(r"https?://\S+", desc or "")
            info_url = url or (m.group(0) if m else None)
            out.append(
                ParseResult(
                    candidate=EventCandidate(
                        name=name,
                        sport_slug=self.sport,
                        start_date=start,
                        end_date=_as_date(comp.get("DTEND")),
                        location=LocationCandidate(text=location, city=city, country=self.country),
                        website=info_url if info_url and info_url.startswith("http") else None,
                        races=[
                            RaceCandidate(
                                name=name,
                                distances=distances_from_text(f"{name} {desc or ''}", self.sport),
                            )
                        ],
                        description=desc,
                        source_url=raw.url,
                        external_id=str(comp.get("UID", "")) or None,
                    ),
                    method="ical",
                    confidence=0.8,
                )
            )
        return out
