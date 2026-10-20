"""World Triathlon connector: parsing of the documented response shape, paging and country filter."""

import re

from app.core.config import get_settings
from app.ingestion.connectors.world_triathlon import (
    OFFICIAL_BASE,
    PUBLIC_MIRROR,
    WorldTriathlonConnector,
    candidate_from_event,
)
from tests.fakes import FakeFetcher

EVENT = {
    "event_id": 90162,
    "event_title": "2027 Hamburg World Triathlon Championship Series",
    "event_slug": "2027-hamburg-world-triathlon-championship-series",
    "event_venue": "Hamburg",
    "event_website": "https://www.hamburg-triathlon.org",
    "event_status": "scheduled",
    "event_date": "2027-07-10",
    "event_finish_date": "2027-07-11",
    "event_country": "Germany",
    "event_country_isoa2": "DE",
    "event_region_id": 10,
    "event_region_name": "Europe",
    "event_latitude": 53.5511,
    "event_longitude": 9.9937,
    "event_categories": [{"cat_id": 351, "cat_name": "World Triathlon Championship Series"}],
    "event_specifications": [{"cat_id": 357, "cat_name": "Triathlon"}, {"cat_id": 360, "cat_name": "Sprint"}],
    "event_listing": "https://www.triathlon.org/events/2027-hamburg",
    "event_api_listing": "https://api.triathlon.org/v1/events/90162",
}
PROGRAMS = [
    {"prog_name": "Elite Men", "prog_date": "2027-07-10", "prog_time": "14:00:00",
     "prog_distances": [{"segment": "Swim", "distance": 750}, {"segment": "Bike", "distance": 20},
                        {"segment": "Run", "distance": 5}]},
    {"prog_name": "Age Group Standard 1.5/40/10", "prog_date": "2027-07-11", "prog_time": "08:00:00"},
    {"prog_name": "Mixed Relay", "prog_date": "2027-07-11", "prog_time": "15:00:00"},
]


def test_candidate_mapping():
    c = candidate_from_event(EVENT, PROGRAMS, "https://api.triathlon.org/v1/events/90162")
    assert c is not None
    assert c.sport_slug == "triathlon" and c.external_id == "90162"
    assert c.start_date.isoformat() == "2027-07-10" and c.end_date.isoformat() == "2027-07-11"
    assert c.location.country == "DE" and c.location.city == "Hamburg" and c.location.lat == 53.5511
    assert str(c.registration_url) == "https://www.hamburg-triathlon.org/"
    assert len(c.races) == 3
    elite, ag, relay = c.races
    assert elite.distances == {"swim_m": 750.0, "bike_km": 20.0, "run_km": 5.0}
    assert elite.discipline_slug == "sprint"  # from event specification
    assert elite.start_time is not None and elite.start_time.hour == 14
    assert ag.distances == {"swim_m": 1500.0, "bike_km": 40.0, "run_km": 10.0}
    assert relay.relay is True
    assert c.status == "scheduled"


def test_cancelled_status_and_no_programs():
    ev = {**EVENT, "event_status": "cancelled", "event_website": None}
    c = candidate_from_event(ev, None, "https://api.triathlon.org/v1/events/90162")
    assert c.status == "cancelled"
    assert c.registration_url is None and str(c.website).startswith("https://www.triathlon.org/")
    assert len(c.races) == 1 and c.races[0].discipline_slug == "sprint"


def _handler(url: str):
    if "/events?" in url:
        page = int(re.search(r"[?&]page=(\d+)", url).group(1))
        data = [EVENT] if page == 1 else [{**EVENT, "event_id": 1, "event_country_isoa2": "FR"}]
        return 200, {"data": data, "current_page": page, "last_page": 2}
    return 200, {"data": {**EVENT, "programs": PROGRAMS}}


async def test_keyless_mirror_pages_filters_and_fetches_programs(monkeypatch):
    monkeypatch.delenv("WORLD_TRIATHLON_API_KEY", raising=False)
    get_settings.cache_clear()
    conn = WorldTriathlonConnector({"countries": ["DE"], "per_page": 50})
    assert conn.base_url == PUBLIC_MIRROR
    f = FakeFetcher(_handler)
    items = [i async for i in conn.discover(f)]
    assert [i.external_id for i in items] == ["90162"]  # FR event filtered out
    assert all(c.url.startswith(PUBLIC_MIRROR) for c in f.calls)
    assert all("apikey" not in (c.headers or {}) for c in f.calls)
    assert len([c for c in f.calls if "/events?" in c.url]) == 2  # both pages visited
    raw = await conn.fetch(items[0], f)
    assert raw.url == f"{PUBLIC_MIRROR}/events/90162"
    results = await conn.parse(raw)
    assert results[0].method == "api" and len(results[0].candidate.races) == 3


async def test_official_api_with_key_sends_header(monkeypatch):
    monkeypatch.setenv("WORLD_TRIATHLON_API_KEY", "k-123")
    get_settings.cache_clear()
    try:
        conn = WorldTriathlonConnector({"countries": ["DE"]})
        assert conn.base_url == OFFICIAL_BASE
        f = FakeFetcher(_handler)
        [i async for i in conn.discover(f)]
        assert all(c.headers and c.headers["apikey"] == "k-123" for c in f.calls)
    finally:
        monkeypatch.delenv("WORLD_TRIATHLON_API_KEY")
        get_settings.cache_clear()


def test_non_race_programs_are_skipped():
    progs = [*PROGRAMS, {"prog_name": "Elite Coaches", "is_race": False, "prog_date": "2027-07-11"}]
    c = candidate_from_event(EVENT, progs, "https://x.test/1")
    assert [r.name for r in c.races] == ["Elite Men", "Age Group Standard 1.5/40/10", "Mixed Relay"]
    assert str(c.source_url) == "https://www.triathlon.org/events/2027-hamburg"  # public listing
