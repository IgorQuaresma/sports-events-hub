from datetime import date

from app.ingestion.normalize import classify_discipline, data_quality_score, normalize
from app.schemas.candidate import EventCandidate, RaceCandidate


def test_triathlon_by_distances():
    r = RaceCandidate(name="Jedermann", distances={"swim_m": 1500, "bike_km": 40, "run_km": 10})
    assert classify_discipline("triathlon", r) == "olympic"
    r = RaceCandidate(name="x", distances={"swim_m": 1.9, "bike_km": 90, "run_km": 21})
    assert classify_discipline("triathlon", r) == "other"  # swim in km not recognised → name/other
    r = RaceCandidate(name="x", distances={"swim_m": 1900, "bike_km": 88, "run_km": 21})
    assert classify_discipline("triathlon", r) == "middle"


def test_running_by_distance_and_name():
    assert (
        classify_discipline("running", RaceCandidate(name="x", distances={"run_km": 21.1}))
        == "half-marathon"
    )
    assert (
        classify_discipline("running", RaceCandidate(name="x", distances={"run_km": 42.195}))
        == "marathon"
    )
    assert (
        classify_discipline("running", RaceCandidate(name="x", distances={"run_km": 65})) == "ultra"
    )
    assert (
        classify_discipline("running", RaceCandidate(name="Stadt-Halbmarathon")) == "half-marathon"
    )
    assert classify_discipline("running", RaceCandidate(name="Volkslauf")) == "other"


def test_trail_and_swim_thresholds():
    assert (
        classify_discipline("trail-running", RaceCandidate(name="x", distances={"run_km": 20}))
        == "short-trail"
    )
    assert (
        classify_discipline("trail-running", RaceCandidate(name="x", distances={"run_km": 70}))
        == "ultra-trail"
    )
    assert (
        classify_discipline("swimming", RaceCandidate(name="x", distances={"swim_m": 12000}))
        == "marathon-swim"
    )


def test_normalize_units_and_defaults():
    c = EventCandidate(
        name="  Test   Lauf ",
        sport_slug="RUNNING",
        start_date=date(2027, 5, 1),
        source_url="https://example.org/x",
        races=[RaceCandidate(name="10er", distances={"run_m": 10000})],
    )
    n = normalize(c, {"country": "DE"})
    assert n.name == "Test Lauf"
    assert n.sport_slug == "running"
    assert n.location.country == "DE"
    assert n.races[0].distances == {"run_km": 10.0}
    assert n.races[0].discipline_slug == "10k"
    assert 0 <= data_quality_score(n) <= 1
