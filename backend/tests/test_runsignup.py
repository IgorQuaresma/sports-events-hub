"""RunSignup connector: mapping of the documented `/rest/races` shape, paging, filtering."""

import json
from datetime import UTC, datetime, timedelta

from app.ingestion.base import RawDocument
from app.ingestion.connectors.runsignup import (
    RunSignupConnector,
    _distance_km,
    candidate_from_race,
)
from tests.fakes import FakeFetcher

_FUTURE = datetime.now(UTC) + timedelta(days=200)
_PAST = datetime.now(UTC) - timedelta(days=30)


def _us(d: datetime, time: bool = True) -> str:
    return d.strftime("%m/%d/%Y %H:%M") if time else d.strftime("%m/%d/%Y")


RACE = {
    "race_id": 136681,
    "name": "Berlin Charity Run",
    "next_date": _us(_FUTURE, time=False),
    "next_end_date": _us(_FUTURE, time=False),
    "is_draft_race": "F",
    "is_private_race": "F",
    "is_registration_open": "T",
    "description": "<h5>Run <b>for a cause</b></h5><p>Fun &amp; fast.</p>",
    "url": "https://runsignup.com/Race/BE/Berlin/BerlinCharityRun",
    "external_race_url": "https://charity-run.example.org",
    "timezone": "Europe/Berlin",
    "address": {"street": "Straße des 17. Juni", "city": "Berlin", "state": "BE",
                "zipcode": "10589", "country_code": "DE"},
    "events": [
        {"event_id": 1, "name": "Half Marathon", "start_time": _us(_FUTURE), "distance": "13.1 Miles",
         "event_type": "running_race",
         "registration_periods": [{"registration_opens": _us(_PAST), "registration_closes": _us(_FUTURE),
                                   "race_fee": "€45.00", "processing_fee": "€3.00"}]},
        {"event_id": 2, "name": "10K", "start_time": _us(_FUTURE), "distance": "10K",
         "event_type": "running_race", "registration_periods": []},
        {"event_id": 3, "name": "Virtual 5K", "distance": "5K", "event_type": "virtual_race"},
    ],
}


def test_candidate_mapping():
    c = candidate_from_race(RACE, "https://runsignup.com/rest/race/136681")
    assert c is not None
    assert c.sport_slug == "running" and c.external_id == "runsignup:136681"
    assert c.location.city == "Berlin" and c.location.country == "DE" and c.location.region == "BE"
    assert str(c.registration_url) == RACE["url"] and str(c.website).startswith("https://charity-run")
    assert c.description == "Run for a cause Fun & fast."  # HTML stripped
    assert [r.name for r in c.races] == ["Half Marathon", "10K"]  # virtual event dropped
    half = c.races[0]
    assert half.distances == {"run_km": 21.082}
    assert half.start_time.tzinfo is not None and str(half.start_time.tzinfo) == "Europe/Berlin"
    assert half.registration.state == "open"
    assert half.registration.prices[0].amount == 45.0 and half.registration.prices[0].currency == "EUR"


def test_registration_not_open_yet():
    later = _FUTURE + timedelta(days=10)
    race = {**RACE, "is_registration_open": "F", "events": [
        {**RACE["events"][0], "registration_periods": [
            {"registration_opens": _us(_FUTURE), "registration_closes": _us(later), "race_fee": "$30"}]}]}
    reg = candidate_from_race(race, "https://x").races[0].registration
    assert reg.state == "not_open" and reg.prices[0].currency == "USD"


def test_virtual_only_race_is_skipped():
    race = {**RACE, "name": "Virtual Challenge", "events": [RACE["events"][2]]}
    assert candidate_from_race(race, "https://x") is None


def test_distance_parsing():
    assert _distance_km("26.2 Miles") == 42.165
    assert _distance_km("10K") == 10 and _distance_km("400 m") == 0.4 and _distance_km("") is None


async def test_discover_pages_and_skips_private_races():
    rows = [{"race": {**RACE, "race_id": i}} for i in range(3)] + [
        {"race": {**RACE, "race_id": 99, "is_private_race": "T"}}
    ]

    def handler(url: str):
        page = 1 if "page=1" in url else 2
        return 200, {"races": rows if page == 1 else []}

    conn = RunSignupConnector({"countries": ["DE"], "per_page": 4})
    f = FakeFetcher(handler)
    items = [i async for i in conn.discover(f)]
    assert [i.external_id for i in items] == ["0", "1", "2"]
    assert len(f.calls) == 2 and "country=DE" in f.calls[0].url and "events=T" in f.calls[0].url
    assert f.calls[0].secret_params is None  # no credentials configured
    raw = await conn.fetch(items[0], f)
    assert isinstance(raw, RawDocument) and json.loads(raw.body)["race_id"] == 0
    results = await conn.parse(raw)
    assert results and results[0].method == "api"
