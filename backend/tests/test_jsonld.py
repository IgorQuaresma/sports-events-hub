import asyncio
from datetime import UTC, datetime

from app.ingestion.base import RawDocument
from app.ingestion.connectors.jsonld import JsonLdConnector, distances_from_text

HTML = b"""<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"SportsEvent","name":"Musterstadt Triathlon 2027",
 "startDate":"2027-06-12T08:00:00+02:00","endDate":"2027-06-12",
 "url":"https://example.org/tri","description":"Olympische Distanz 1,5 / 40 / 10 km",
 "location":{"@type":"Place","name":"Stadtsee","address":{"@type":"PostalAddress",
   "streetAddress":"Seeweg 1","postalCode":"12345","addressLocality":"Musterstadt",
   "addressRegion":"Bayern","addressCountry":"DE"},"geo":{"latitude":48.1,"longitude":11.5}},
 "organizer":{"@type":"Organization","name":"TSV Muster"},
 "offers":{"@type":"Offer","price":"89.00","priceCurrency":"EUR","url":"https://example.org/tri/anmeldung",
   "availability":"https://schema.org/InStock","validFrom":"2026-11-01T10:00:00+01:00"},
 "subEvent":[{"@type":"SportsEvent","name":"Sprint 750/20/5","startDate":"2027-06-12T10:00:00+02:00"}]}
</script></head><body>irrelevant <script>alert(1)</script></body></html>"""


def test_distances_from_text():
    assert distances_from_text("1,5 / 40 / 10 km", "triathlon") == {
        "swim_m": 1500.0,
        "bike_km": 40.0,
        "run_km": 10.0,
    }
    assert distances_from_text("750 m – 20 km – 5 km", "triathlon") == {
        "swim_m": 750.0,
        "bike_km": 20.0,
        "run_km": 5.0,
    }
    assert distances_from_text("Halbmarathon 21,1 km", "running") == {"run_km": 21.1}


def test_jsonld_parse():
    conn = JsonLdConnector({"sport_slug": "triathlon", "platform": "organizer"})
    raw = RawDocument(
        url="https://example.org/tri", body=HTML, fetched_at=datetime.now(UTC), http_status=200
    )
    results = asyncio.run(conn.parse(raw))
    assert len(results) == 1
    c = results[0].candidate
    assert c.name == "Musterstadt Triathlon 2027"
    assert c.start_date.isoformat() == "2027-06-12"
    assert (
        c.location.city == "Musterstadt" and c.location.country == "DE" and c.location.lat == 48.1
    )
    assert c.organizer_name == "TSV Muster"
    assert str(c.registration_url) == "https://example.org/tri/anmeldung"
    assert len(c.races) == 1 and c.races[0].distances == {
        "swim_m": 750.0,
        "bike_km": 20.0,
        "run_km": 5.0,
    }
    assert results[0].method == "jsonld"
