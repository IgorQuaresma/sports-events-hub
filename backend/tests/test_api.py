"""API tests against the test database: ingest candidates → search → detail → redirect."""

import pytest

from app.core.config import get_settings

CANDIDATES = [
    {
        "name": "Testsee Triathlon",
        "sport_slug": "triathlon",
        "start_date": "2027-06-05",
        "location": {"city": "Hamburg", "country": "DE", "lat": 53.55, "lon": 9.99},
        "organizer_name": "Test e.V.",
        "website": "https://example.org/testsee",
        "registration_url": "https://example.org/testsee/register",
        "registration_platform": "organizer",
        "source_url": "https://example.org/testsee",
        "races": [
            {
                "name": "Olympic",
                "distances": {"swim_m": 1500, "bike_km": 40, "run_km": 10},
                "attributes": {
                    "wetsuit_rule": "allowed",
                    "course_profile": "flat",
                    "elevation_gain_m": 100,
                },
                "registration": {
                    "state": "open",
                    "prices": [{"label": "Regular", "amount": 99, "currency": "EUR"}],
                },
            }
        ],
    },
    {
        "name": "Bergsee Triathlon",
        "sport_slug": "triathlon",
        "start_date": "2027-07-10",
        "location": {"city": "Innsbruck", "country": "AT", "lat": 47.27, "lon": 11.40},
        "source_url": "https://example.org/bergsee",
        "races": [
            {
                "name": "Olympic",
                "distances": {"swim_m": 1500, "bike_km": 40, "run_km": 10},
                "attributes": {
                    "wetsuit_rule": "mandatory",
                    "course_profile": "mountain",
                    "elevation_gain_m": 900,
                },
            }
        ],
    },
]


def _auth():
    return {"Authorization": f"Bearer {get_settings().service_token.get_secret_value()}"}


@pytest.fixture(scope="module", autouse=True)
async def ingested():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/ingest/candidates?source_key=test", json=CANDIDATES, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 2
        # second push with identical content is an update, not a duplicate
        r = await c.post("/v1/ingest/candidates?source_key=test", json=CANDIDATES, headers=_auth())
        assert r.json()["created"] == 0 and r.json()["updated"] == 2


async def test_ingest_requires_token(client):
    r = await client.post("/v1/ingest/candidates", json=[])
    assert r.status_code == 401


async def test_search_filters_and_facets(client):
    r = await client.get("/v1/search", params={"sport": "triathlon", "country": "DE"})
    body = r.json()
    assert body["total"] == 1
    hit = body["results"][0]
    assert hit["event_name"] == "Testsee Triathlon" and hit["reg_state"] == "open"
    assert float(hit["price_from"]) == 99.0
    assert body["facets"]["country"] == {"DE": 1}

    r = await client.get("/v1/search", params={"attr": ["elevation_gain_m<=200"]})
    assert [h["event_name"] for h in r.json()["results"]] == ["Testsee Triathlon"]

    r = await client.get("/v1/search", params={"attr": ["wetsuit_rule:mandatory"]})
    assert [h["event_name"] for h in r.json()["results"]] == ["Bergsee Triathlon"]

    r = await client.get(
        "/v1/search", params={"near": "53.5,10.0", "radius_km": 50, "sort": "distance"}
    )
    assert r.json()["total"] == 1 and r.json()["results"][0]["distance_km"] < 10

    r = await client.get("/v1/search", params={"q": "bergsee"})
    assert r.json()["results"][0]["event_name"] == "Bergsee Triathlon"


async def test_parse_then_structured_search(client):
    r = await client.post("/v1/search/parse", json={"query": "olympic triathlon austria wetsuit"})
    parsed = r.json()
    assert parsed["method"] == "rules" and parsed["filters"]["country"] == ["AT"]
    r = await client.post("/v1/search/structured", json=parsed["filters"])
    assert r.json()["total"] == 1


async def test_event_detail_and_redirect(client):
    r = await client.get("/v1/events/testsee-triathlon")
    assert r.status_code == 200
    ev = r.json()
    ne = ev["next_edition"]
    assert ne["venue"]["city"] == "Hamburg"
    assert ne["races"][0]["discipline_slug"] == "olympic"
    assert ne["races"][0]["registration"]["price_tiers"][0]["label"] == "Regular"
    assert ne["provenance"][0]["parse_method"] == "api"

    r = await client.get(f"/v1/editions/{ne['id']}/go")
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.org/testsee/register"

    r = await client.get("/v1/events/does-not-exist")
    assert r.status_code == 404


async def test_taxonomy(client):
    r = await client.get("/v1/taxonomy")
    slugs = {s["slug"] for s in r.json()["sports"]}
    assert {"triathlon", "running", "hyrox"} <= slugs


@pytest.mark.parametrize(
    "params",
    [{"near": "not-a-point"}, {"attr": ["elevation_gain_m<=lots"]}, {"sort": "random"},
     {"limit": 1000}, {"radius_km": -5}, {"q": "x" * 300}],
)
async def test_invalid_search_params_are_422_not_500(client, params):
    r = await client.get("/v1/search", params=params)
    assert r.status_code == 422, r.text


async def test_source_filter_facet_and_demo_toggle(client):
    body = (await client.get("/v1/search")).json()
    assert body["facets"]["source"].get("test") == 2
    assert all(h["source_keys"] == ["test"] for h in body["results"])
    r = await client.get("/v1/search", params={"source": "nope"})
    assert r.json()["total"] == 0
    r = await client.get("/v1/search", params={"include_demo": "false"})
    assert r.json()["total"] == 2  # test data is not demo data


async def test_public_sources_endpoint_hides_internals(client):
    r = await client.get("/v1/sources")
    assert r.status_code == 200
    body = r.json()
    src = next(s for s in body["sources"] if s["key"] == "test")
    assert src["editions"] == 2 and "config" not in src and "last_error" not in src
    assert {p["key"] for p in body["enrichment"]} == {"open-meteo", "nominatim"}


async def test_calendar_and_weather(client):
    ev = (await client.get("/v1/events/testsee-triathlon")).json()
    assert ev["is_demo"] is False and ev["next_edition"]["provenance"][0]["source_key"] == "test"
    ed = ev["next_edition"]["id"]
    r = await client.get(f"/v1/editions/{ed}/calendar.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "DTSTART;VALUE=DATE:20270605" in r.text and "DTEND;VALUE=DATE:20270606" in r.text
    assert "SUMMARY:Testsee Triathlon 2027" in r.text and "\r\n" in r.text
    w = (await client.get(f"/v1/editions/{ed}/weather")).json()
    assert w["available"] is False and w["reason"] == "too_far_ahead"


async def test_security_headers_and_admin_redaction(client):
    r = await client.get("/healthz")
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert r.headers["x-content-type-options"] == "nosniff"
    r = await client.get("/v1/admin/sources", headers=_auth())
    assert r.status_code == 200 and all("config" in s for s in r.json())
    r = await client.get("/v1/admin/sources")
    assert r.status_code == 401


async def test_outbound_click_stores_no_raw_ip(client):
    from sqlalchemy import select

    from app.core.db import get_session_factory
    from app.models import OutboundClick

    ev = (await client.get("/v1/events/testsee-triathlon")).json()
    r = await client.get(f"/v1/editions/{ev['next_edition']['id']}/go")
    assert r.status_code == 302 and r.headers["referrer-policy"] == "no-referrer"
    async with get_session_factory()() as s:
        click = (await s.execute(select(OutboundClick).order_by(OutboundClick.id.desc()))).scalars().first()
    assert click is not None and len(click.anon_session_hash) == 64
    assert "127.0.0.1" not in click.anon_session_hash
