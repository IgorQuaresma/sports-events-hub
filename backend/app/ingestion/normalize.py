"""Normalization: canonical units, discipline classification, cleanup."""

from __future__ import annotations

import re

from app.schemas.candidate import EventCandidate, RaceCandidate
from app.search.nlq import DISCIPLINE_PATTERNS
from app.taxonomy import DISCIPLINES

_DISC_BY_SPORT: dict[str, list[tuple[str, dict | None]]] = {}
for sport, slug, _de, _en, dist in DISCIPLINES:
    _DISC_BY_SPORT.setdefault(sport, []).append((slug, dist))

_VALID = {(s, d) for s, d, *_ in DISCIPLINES}


def _close(a: float | None, b: float | None, tol: float = 0.15) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * b


def classify_discipline(sport: str, race: RaceCandidate) -> str:
    """Pick a discipline slug from explicit slug, distances, then name keywords."""
    if race.discipline_slug and (sport, race.discipline_slug) in _VALID:
        return race.discipline_slug

    d = race.distances
    if sport == "triathlon":
        if race.relay:
            return "relay"
        for slug, canon in _DISC_BY_SPORT["triathlon"]:
            if (
                canon
                and _close(d.get("swim_m"), canon["swim_m"])
                and _close(d.get("bike_km"), canon["bike_km"])
            ):
                return slug
    if sport == "running" and d.get("run_km"):
        km = d["run_km"]
        if km > 45:
            return "ultra"
        for slug, canon in _DISC_BY_SPORT["running"]:
            if canon and _close(km, canon["run_km"], 0.08):
                return slug
    if sport == "trail-running" and (d.get("run_km") or d.get("total_km")):
        km = d.get("run_km") or d["total_km"]
        return "short-trail" if km < 25 else "trail-marathon" if km <= 45 else "ultra-trail"
    if sport == "swimming" and (d.get("swim_m") or d.get("total_km")):
        km = (d.get("swim_m") or 0) / 1000 or d.get("total_km", 0)
        return "open-water" if km <= 5 else "marathon-swim" if km <= 25 else "ultra-swim"
    if sport == "ocr" and (d.get("run_km") or d.get("total_km")):
        km = d.get("run_km") or d["total_km"]
        return "short" if km < 10 else "standard" if km <= 15 else "long"

    name = race.name.lower()
    for pat, s, disc in DISCIPLINE_PATTERNS:
        if s == sport and re.search(pat, name, re.IGNORECASE):
            return disc
    if sport == "hyrox":
        return "doubles" if "double" in name else "pro" if "pro" in name else "open"
    if sport == "cycling":
        return "gravel" if "gravel" in name else "mtb-marathon" if "mtb" in name else "gran-fondo"
    if sport == "hiking":
        return "mega-march" if re.search(r"mega|mammut|24", name) else "day-hike"

    slugs = [s for s, _ in _DISC_BY_SPORT.get(sport, [])]
    return "other" if "other" in slugs else (slugs[0] if slugs else "other")


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def normalize(c: EventCandidate, defaults: dict | None = None) -> EventCandidate:
    defaults = defaults or {}
    c = c.model_copy(deep=True)
    c.name = _clean(c.name) or c.name
    c.sport_slug = c.sport_slug.lower().strip()
    if c.location.country is None and defaults.get("country"):
        c.location.country = defaults["country"]
    c.location.city = _clean(c.location.city)
    if c.end_date and c.end_date < c.start_date:
        c.end_date = None
    if not c.races:
        c.races = [RaceCandidate(name=c.name)]
    for r in c.races:
        r.name = _clean(r.name) or c.name
        # unit coercion: accept swim_km / bike_m / run_m variants
        d = dict(r.distances)
        if "swim_km" in d:
            d["swim_m"] = d.pop("swim_km") * 1000
        if "bike_m" in d:
            d["bike_km"] = d.pop("bike_m") / 1000
        if "run_m" in d:
            d["run_km"] = d.pop("run_m") / 1000
        r.distances = {k: round(float(v), 3) for k, v in d.items() if v is not None}
        r.discipline_slug = classify_discipline(c.sport_slug, r)
        if r.registration and r.registration.url is None and c.registration_url:
            r.registration.url = c.registration_url
    return c


def data_quality_score(c: EventCandidate) -> float:
    checks = [
        bool(c.location.city),
        c.location.lat is not None and c.location.lon is not None,
        bool(c.registration_url or any(r.registration and r.registration.url for r in c.races)),
        any(r.distances for r in c.races),
        any(r.registration and r.registration.state != "unknown" for r in c.races),
        any(r.registration and r.registration.prices for r in c.races),
        bool(c.website),
        bool(c.description),
    ]
    return round(sum(checks) / len(checks), 2)
