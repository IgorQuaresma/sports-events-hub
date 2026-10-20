"""Ticketmaster connector: Discovery API v2 mapping, sport filtering, key handling."""

import pytest

from app.core.config import get_settings
from app.ingestion.connectors.ticketmaster import TicketmasterConnector, candidate_from_event
from tests.fakes import FakeFetcher

HYROX = {
    "id": "Z698xZb_Z17",
    "name": "HYROX Hamburg",
    "url": "https://www.ticketmaster.de/event/hyrox-hamburg-tickets/123",
    "dates": {"start": {"localDate": "2027-03-20", "dateTime": "2027-03-20T08:00:00Z"},
              "end": {"localDate": "2027-03-21"}, "status": {"code": "onsale"}},
    "sales": {"public": {"startDateTime": "2026-09-01T08:00:00Z", "endDateTime": "2027-03-19T22:00:00Z"}},
    "classifications": [{"segment": {"name": "Sports"}, "genre": {"name": "Miscellaneous"}}],
    "priceRanges": [{"type": "standard", "currency": "EUR", "min": 99.0, "max": 139.0}],
    "promoter": {"name": "HYROX GmbH"},
    "_embedded": {"venues": [{
        "name": "Messe Hamburg", "postalCode": "20357", "city": {"name": "Hamburg"},
        "country": {"countryCode": "DE"}, "address": {"line1": "Messeplatz 1"},
        "location": {"latitude": "53.5627", "longitude": "9.9822"}}]},
}
CONCERT = {**HYROX, "id": "c1", "name": "Run-DMC Live",
           "classifications": [{"segment": {"name": "Music"}, "genre": {"name": "Hip-Hop/Rap"}}]}


def test_mapping():
    c = candidate_from_event(HYROX)
    assert c.sport_slug == "hyrox" and c.external_id == "ticketmaster:Z698xZb_Z17"
    assert c.start_date.isoformat() == "2027-03-20" and c.end_date.isoformat() == "2027-03-21"
    assert c.location.city == "Hamburg" and c.location.lat == 53.5627 and c.location.country == "DE"
    reg = c.races[0].registration
    assert reg.state == "open" and reg.prices[0].amount == 99.0 and reg.platform == "ticketmaster"
    assert c.organizer_name == "HYROX GmbH"


def test_non_sport_and_cancelled():
    assert candidate_from_event(CONCERT) is None
    cancelled = {**HYROX, "dates": {**HYROX["dates"], "status": {"code": "cancelled"}}}
    assert candidate_from_event(cancelled).status == "cancelled"


async def test_requires_key(monkeypatch):
    monkeypatch.delenv("TICKETMASTER_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="TICKETMASTER_API_KEY"):
        [i async for i in TicketmasterConnector({}).discover(FakeFetcher(lambda u: (200, {})))]


async def test_key_is_secret_param_and_results_deduplicated(monkeypatch):
    monkeypatch.setenv("TICKETMASTER_API_KEY", "tm-secret-key")
    get_settings.cache_clear()
    try:
        page = {"_embedded": {"events": [HYROX, CONCERT]}, "page": {"totalPages": 1}}
        f = FakeFetcher(lambda u: (200, page))
        conn = TicketmasterConnector({"countries": ["DE"], "keywords": ["hyrox", "run"]})
        items = [i async for i in conn.discover(f)]
        assert sorted(i.external_id for i in items) == ["Z698xZb_Z17", "c1"]  # deduped across keywords
        assert len(f.calls) == 2
        for c in f.calls:
            assert "tm-secret-key" not in c.url
            assert c.secret_params == {"apikey": "tm-secret-key"}
        parsed = [await conn.parse(await conn.fetch(i, f)) for i in items]
        assert sum(len(p) for p in parsed) == 1  # the concert is dropped at parse time
    finally:
        monkeypatch.delenv("TICKETMASTER_API_KEY")
        get_settings.cache_clear()
