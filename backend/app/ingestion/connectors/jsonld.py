"""Generic organizer-page connector: reads schema.org `Event`/`SportsEvent` JSON-LD.

Config: {"urls": [...], "sport_slug": "triathlon", "country": "DE", "platform": "raceresult"}
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from dateutil import parser as dtparser
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.schemas.candidate import (
    EventCandidate,
    LocationCandidate,
    PriceCandidate,
    RaceCandidate,
    RegistrationCandidate,
)

_AVAILABILITY = {
    "instock": "open",
    "limitedavailability": "open",
    "onlineonly": "open",
    "soldout": "sold_out",
    "preorder": "not_open",
    "presale": "not_open",
    "discontinued": "closed",
    "outofstock": "sold_out",
}

_DIST_RE = re.compile(
    r"(?P<swim>\d+(?:[.,]\d+)?)\s*(?:m|km)?\s*[/|–-]\s*(?P<bike>\d+(?:[.,]\d+)?)\s*(?:km)?\s*[/|–-]\s*"
    r"(?P<run>\d+(?:[.,]\d+)?)\s*(?:km)?"
)


def _num(v: str) -> float:
    return float(v.replace(",", "."))


def distances_from_text(text: str, sport: str) -> dict[str, float]:
    """'1.5 / 40 / 10' or '1500 m – 40 km – 10 km' → swim_m/bike_km/run_km (triathlon)."""
    m = _DIST_RE.search(text)
    if sport == "triathlon" and m:
        swim = _num(m["swim"])
        swim_m = swim * 1000 if swim < 10 else swim
        return {"swim_m": swim_m, "bike_km": _num(m["bike"]), "run_km": _num(m["run"])}
    km = re.search(r"(\d+(?:[.,]\d+)?)\s*km", text, re.IGNORECASE)
    if km and sport in ("running", "trail-running", "hiking", "ocr", "cycling"):
        key = "run_km" if sport != "cycling" else "bike_km"
        return {key: _num(km.group(1))}
    return {}


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _parse_date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return dtparser.isoparse(str(v)).date()
    except (ValueError, TypeError):
        try:
            return dtparser.parse(str(v)).date()
        except (ValueError, TypeError):
            return None


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return dtparser.isoparse(str(v))
    except (ValueError, TypeError):
        return None


def _location(node: Any) -> LocationCandidate:
    loc = _first(node) or {}
    if isinstance(loc, str):
        return LocationCandidate(text=loc)
    addr = loc.get("address") or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    geo = loc.get("geo") or {}
    country = addr.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name")
    if country and len(country) > 2:
        country = {
            "germany": "DE",
            "deutschland": "DE",
            "austria": "AT",
            "österreich": "AT",
            "switzerland": "CH",
            "schweiz": "CH",
        }.get(country.lower(), country[:2])
    return LocationCandidate(
        name=loc.get("name"),
        street=addr.get("streetAddress"),
        postal_code=addr.get("postalCode"),
        city=addr.get("addressLocality"),
        region=addr.get("addressRegion"),
        country=country,
        lat=float(geo["latitude"]) if geo.get("latitude") is not None else None,
        lon=float(geo["longitude"]) if geo.get("longitude") is not None else None,
    )


def _registration(offers: Any) -> RegistrationCandidate | None:
    offers = offers if isinstance(offers, list) else ([offers] if offers else [])
    if not offers:
        return None
    reg = RegistrationCandidate()
    for o in offers:
        if not isinstance(o, dict):
            continue
        avail = str(o.get("availability", "")).split("/")[-1].lower()
        if avail in _AVAILABILITY:
            reg.state = _AVAILABILITY[avail]
        reg.url = reg.url or o.get("url")
        reg.opens_at = reg.opens_at or _parse_dt(o.get("validFrom"))
        reg.closes_at = reg.closes_at or _parse_dt(o.get("validThrough"))
        price = o.get("price") or (o.get("priceSpecification") or {}).get("price")
        if price not in (None, ""):
            try:
                reg.prices.append(
                    PriceCandidate(
                        label=o.get("name"),
                        amount=float(str(price).replace(",", ".")),
                        currency=o.get("priceCurrency", "EUR"),
                        valid_from=_parse_dt(o.get("validFrom")),
                        valid_until=_parse_dt(o.get("validThrough")),
                    )
                )
            except ValueError:
                pass
    return reg


def _is_event(node: dict) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(str(x).endswith(("Event", "SportsEvent")) for x in types if x)


def iter_event_nodes(data: Any):
    if isinstance(data, list):
        for d in data:
            yield from iter_event_nodes(d)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from iter_event_nodes(data["@graph"])
        if _is_event(data):
            yield data


def extract_jsonld_blocks(html: bytes) -> list[Any]:
    tree = HTMLParser(html)
    out: list[Any] = []
    for node in tree.css('script[type="application/ld+json"]'):
        txt = node.text(strip=True)
        if not txt:
            continue
        try:
            out.append(json.loads(txt))
        except json.JSONDecodeError:
            continue
    return out


def candidate_from_node(
    node: dict, source_url: str, sport: str, platform: str | None
) -> EventCandidate | None:
    start = _parse_date(node.get("startDate"))
    name = node.get("name")
    if not start or not name:
        return None
    races: list[RaceCandidate] = []
    subs = node.get("subEvent") or []
    subs = subs if isinstance(subs, list) else [subs]
    for sub in subs:
        if not isinstance(sub, dict) or not sub.get("name"):
            continue
        races.append(
            RaceCandidate(
                name=sub["name"],
                start_time=_parse_dt(sub.get("startDate")),
                distances=distances_from_text(f"{sub['name']} {sub.get('description', '')}", sport),
                registration=_registration(sub.get("offers")),
            )
        )
    reg = _registration(node.get("offers"))
    if not races:
        races.append(
            RaceCandidate(
                name=name,
                distances=distances_from_text(f"{name} {node.get('description', '')}", sport),
                registration=reg,
            )
        )
    organizer = node.get("organizer")
    organizer_name = organizer.get("name") if isinstance(organizer, dict) else organizer
    reg_url = (reg.url if reg else None) or None
    return EventCandidate(
        name=name,
        sport_slug=sport,
        start_date=start,
        end_date=_parse_date(node.get("endDate")),
        location=_location(node.get("location")),
        organizer_name=organizer_name,
        website=node.get("url") if str(node.get("url", "")).startswith("http") else None,
        registration_url=str(reg_url) if reg_url else None,
        registration_platform=platform,
        races=races,
        description=(node.get("description") or None),
        source_url=source_url,
        external_id=node.get("@id") or node.get("identifier"),
    )


class JsonLdConnector:
    key = "jsonld"

    def __init__(self, config: dict[str, Any]) -> None:
        self.urls: list[str] = config.get("urls", [])
        self.sport = config.get("sport_slug", "running")
        self.platform = config.get("platform")

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        for u in self.urls:
            yield DiscoveredItem(url=u)

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        return await fetcher.get(item.url)

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        results: list[ParseResult] = []
        for block in extract_jsonld_blocks(raw.body):
            for node in iter_event_nodes(block):
                cand = candidate_from_node(node, raw.url, self.sport, self.platform)
                if cand:
                    results.append(ParseResult(candidate=cand, method="jsonld", confidence=0.9))
        return results
