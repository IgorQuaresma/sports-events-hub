"""Built-in data sources: one declarative entry per real API (see docs/DATA_SOURCES.md).

`python -m app.cli sync-sources` registers every entry whose required credentials are set;
`GET /v1/sources` exposes the public part (name, homepage, licence, attribution) to the UI.
Secrets are referenced by *setting name* only — the values stay in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    connector: str
    kind: str  # api | feed | scrape | submission | manual
    trust: int
    homepage: str
    docs_url: str
    license: str
    attribution: str
    config: dict[str, Any] = field(default_factory=dict)
    requires: tuple[str, ...] = ()  # Settings attribute names that must be non-empty
    rate_limit_rps: float = 1.0
    notes: str = ""

    def missing(self, settings: Settings) -> list[str]:
        return [name.upper() for name in self.requires if not settings.secret(name)]

    def available(self, settings: Settings) -> bool:
        return not self.missing(settings)


DACH = ["DE", "AT", "CH"]

CATALOG: list[SourceSpec] = [
    SourceSpec(
        key="world-triathlon",
        name="World Triathlon",
        connector="world_triathlon",
        kind="api",
        trust=80,
        homepage="https://www.triathlon.org/events",
        docs_url="https://developers.triathlon.org",
        license="World Triathlon API terms",
        attribution="Event data © World Triathlon",
        config={"countries": DACH, "region_id": 10, "months_ahead": 18, "fetch_programs": True},
        rate_limit_rps=1.0,
        notes="Keyless public mirror by default; WORLD_TRIATHLON_API_KEY switches to the "
        "official API.",
    ),
    SourceSpec(
        key="runsignup",
        name="RunSignup",
        connector="runsignup",
        kind="api",
        trust=75,
        homepage="https://runsignup.com",
        docs_url="https://runsignup.com/API",
        license="RunSignup API terms",
        attribution="Race data via RunSignup",
        config={"countries": DACH, "months_ahead": 18},
        rate_limit_rps=1.0,
        notes="Public race search, no key needed. Few DACH races; add more countries in config.",
    ),
    SourceSpec(
        key="ticketmaster",
        name="Ticketmaster",
        connector="ticketmaster",
        kind="api",
        trust=70,
        homepage="https://www.ticketmaster.de",
        docs_url="https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/",
        license="Ticketmaster Discovery API terms of use",
        attribution="Event data provided by Ticketmaster",
        config={"countries": DACH, "months_ahead": 12},
        requires=("ticketmaster_api_key",),
        rate_limit_rps=4.0,
        notes="Free key (5000 calls/day). Mostly spectator events; we keep HYROX, runs, etc.",
    ),
    SourceSpec(
        key="wikidata",
        name="Wikidata + organizer websites",
        connector="wikidata",
        kind="api",
        trust=60,
        homepage="https://www.wikidata.org",
        docs_url="https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service",
        license="Wikidata: CC0 · event details: the organizer's own website",
        attribution="Event list from Wikidata (CC0); details from the official event websites",
        config={"countries": DACH, "max_events": 200, "llm_fallback": False},
        rate_limit_rps=1.0,
        notes="Discovers recurring events + official sites on Wikidata, then reads schema.org "
        "JSON-LD from each site (robots.txt respected).",
    ),
]

SAMPLE = SourceSpec(
    key="sample",
    name="Demo data",
    connector="sample_fixture",
    kind="manual",
    trust=10,
    homepage="https://github.com/IgorQuaresma/sports-events-hub",
    docs_url="",
    license="Fictional sample data",
    attribution="Demo data — not real races",
    config={"fixture": "sample_events.json"},
)

# Third-party services used to enrich events (shown on the sources page for attribution)
ENRICHMENT_PROVIDERS: list[dict[str, str]] = [
    {
        "key": "open-meteo",
        "name": "Open-Meteo",
        "purpose": "Race-day weather forecast",
        "homepage": "https://open-meteo.com",
        "license": "CC BY 4.0",
        "attribution": "Weather data by Open-Meteo.com",
    },
    {
        "key": "nominatim",
        "name": "OpenStreetMap Nominatim",
        "purpose": "Geocoding venues without coordinates",
        "homepage": "https://nominatim.openstreetmap.org",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
    },
]

BY_KEY: dict[str, SourceSpec] = {s.key: s for s in [*CATALOG, SAMPLE]}
