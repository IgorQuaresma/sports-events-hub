"""Wikidata discovery connector: SPARQL rows → items → JSON-LD from the official site."""

import json
from datetime import date, timedelta

from app.ingestion.connectors.wikidata import WikidataConnector, build_query, rows_to_items
from tests.fakes import FakeFetcher


def _row(qid, label, web, sport, cc="DE", coord=None):
    b = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"}, "itemLabel": {"value": label},
         "web": {"value": web}, "sport": {"value": sport}, "cc": {"value": cc}}
    if coord:
        b["coord"] = {"value": coord}
    return b


ROWS = [
    _row("Q161222", "Berlin-Marathon", "https://www.bmw-berlin-marathon.com/", "running",
         coord="Point(13.3777 52.5163)"),
    _row("Q1", "UTMB", "https://montblanc.utmb.world/fr/races/utmb", "running", "CH"),
    _row("Q1", "UTMB", "https://montblanc.utmb.world/races/utmb", "trail-running", "CH"),
    _row("Q2", "Q2", "http://insecure.example.org", "running"),
]


def test_rows_collapse_per_item():
    items = {i["qid"]: i for i in rows_to_items(ROWS)}
    assert items["Q161222"]["lat"] == 52.5163 and items["Q161222"]["lon"] == 13.3777
    assert items["Q1"]["sport"] == "trail-running"  # more specific sport wins
    assert items["Q1"]["website"] == "https://montblanc.utmb.world/races/utmb"  # no /fr/
    assert items["Q2"]["label"] is None  # bare QID is not a label


def test_query_mentions_requested_countries_only():
    q = build_query(["AT"])
    assert 'wd:Q40 "AT"' in q and "wd:Q183" not in q and "wdt:P856" in q


def _page(start: date) -> bytes:
    node = {"@context": "https://schema.org", "@type": "SportsEvent", "name": "Berlin-Marathon",
            "startDate": start.isoformat(), "location": {"@type": "Place", "name": "Berlin"},
            "offers": {"@type": "Offer", "url": "https://register.example.org", "price": "150",
                       "priceCurrency": "EUR", "availability": "https://schema.org/InStock"}}
    return f'<html><script type="application/ld+json">{json.dumps(node)}</script></html>'.encode()


async def test_discover_fetch_parse_fills_coordinates():
    upcoming = date.today() + timedelta(days=120)

    def handler(url: str):
        if "query.wikidata.org" in url:
            return 200, {"results": {"bindings": ROWS[:1]}}
        return 200, _page(upcoming)

    conn = WikidataConnector({"countries": ["DE"]})
    f = FakeFetcher(handler)
    items = [i async for i in conn.discover(f)]
    assert len(items) == 1 and f.calls[0].check_robots is False  # SPARQL API only
    raw = await conn.fetch(items[0], f)
    assert f.calls[1].check_robots is True  # organizer websites keep robots.txt checks
    [res] = await conn.parse(raw)
    c = res.candidate
    assert c.sport_slug == "running" and c.start_date == upcoming
    assert c.location.lat == 52.5163 and c.location.country == "DE"
    assert res.method == "jsonld"


async def test_past_editions_and_pages_without_jsonld_yield_nothing():
    conn = WikidataConnector({})
    for body in (_page(date.today() - timedelta(days=5)), b"<html><p>no data</p></html>"):
        f = FakeFetcher(lambda u, b=body: (200, b))
        from app.ingestion.base import DiscoveredItem

        raw = await conn.fetch(DiscoveredItem(url="https://e.example.org", hint={"sport": "running"}), f)
        assert await conn.parse(raw) == []
