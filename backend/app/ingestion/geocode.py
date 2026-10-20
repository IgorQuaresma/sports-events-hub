"""Venue geocoding with OpenStreetMap Nominatim (opt-in via GEOCODING_ENABLED).

Radius search needs coordinates, but several sources (RunSignup, iCal feeds, many JSON-LD
blocks) only give an address. Nominatim usage policy, which this module follows:
  - max 1 request/second, a descriptive User-Agent (+ contact via CONTACT_EMAIL)
  - results cached (here in `geocode_cache`, including misses), no bulk geocoding
  - attribution "© OpenStreetMap contributors" (shown on /sources)
The host is fixed by configuration, never taken from source data (no SSRF surface).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import GeocodeCache
from app.schemas.candidate import EventCandidate, LocationCandidate

log = logging.getLogger("ingest.geocode")

PROVIDER = "nominatim"


def geocode_query(loc: LocationCandidate) -> str | None:
    """City-level query string; street-level precision is not needed for radius search."""
    if not (loc.city or loc.postal_code) or not loc.country:
        return None
    place = " ".join(x for x in [loc.postal_code, loc.city] if x)
    parts = [place, loc.region, loc.country]
    return ", ".join(p.strip() for p in parts if p and p.strip()).lower()


class NominatimGeocoder:
    def __init__(self) -> None:
        s = get_settings()
        headers = {"User-Agent": s.fetcher_user_agent, "Accept": "application/json"}
        if s.contact_email:
            headers["From"] = s.contact_email
        self.base_url = s.nominatim_url.rstrip("/")
        self.email = s.contact_email
        self._client = httpx.AsyncClient(headers=headers, timeout=10.0)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _lookup(self, query: str, country: str) -> tuple[float, float, str] | None:
        async with self._lock:  # strictly sequential, ≥ 1.1 s apart
            wait = 1.1 - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            params = {"q": query, "format": "jsonv2", "limit": "1", "countrycodes": country.lower()}
            if self.email:
                params["email"] = self.email
            try:
                resp = await self._client.get(f"{self.base_url}/search", params=params)
            finally:
                self._last = time.monotonic()
        if resp.status_code != 200:
            log.warning("nominatim HTTP %s for %r", resp.status_code, query)
            return None
        rows = resp.json()
        if not rows:
            return None
        return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name", "")

    async def locate(self, session: AsyncSession, loc: LocationCandidate) -> bool:
        """Fill `loc.lat/lon` in place. Returns True when coordinates were found."""
        query = geocode_query(loc)
        if query is None or loc.country is None:
            return False
        cached = await session.get(GeocodeCache, query)
        if cached is None:
            try:
                hit = await self._lookup(query, loc.country)
            except (httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("geocoding failed for %r: %s", query, e)
                return False  # transient: do not cache
            cached = GeocodeCache(
                query=query,
                provider=PROVIDER,
                lat=hit[0] if hit else None,
                lon=hit[1] if hit else None,
                display_name=hit[2] if hit else None,
            )
            session.add(cached)
            await session.flush()
        if cached.lat is None or cached.lon is None:
            return False
        loc.lat, loc.lon = cached.lat, cached.lon
        return True


async def enrich_coordinates(
    session: AsyncSession, cand: EventCandidate, geocoder: NominatimGeocoder | None
) -> EventCandidate:
    if geocoder is None or (cand.location.lat is not None and cand.location.lon is not None):
        return cand
    await geocoder.locate(session, cand.location)
    return cand
