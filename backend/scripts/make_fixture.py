"""Generates backend/data/fixtures/sample_events.json — DEMO DATA for development and testing.

Deterministic (seeded) generator producing ~90 fictional events across DACH (mostly Germany) with
realistic variety: all sports and disciplines, Nov 2026 – Dec 2027 dates plus a few past 2026
editions (so events show history), every registration state, price tiers with validity, relays,
participant counters, cancelled/postponed editions, and mixed data completeness.

These are NOT real races. Organizer is always "Demo Organizer (sample data)" and the description
says so; the UI shows a demo banner for them.

Run: python scripts/make_fixture.py
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20261019
rng = random.Random(SEED)
TODAY = date(2026, 10, 19)
DEMO_NOTE = "Demo event — sample data for development, not a real race."
ORG = "Demo Organizer (sample data)"

# city: (country, lat, lon, region)
CITIES: dict[str, tuple[str, float, float, str]] = {
    # Germany — spread over all Bundesländer
    "Hamburg": ("DE", 53.551, 9.994, "Hamburg"),
    "Berlin": ("DE", 52.520, 13.405, "Berlin"),
    "München": ("DE", 48.137, 11.575, "Bayern"),
    "Nürnberg": ("DE", 49.453, 11.077, "Bayern"),
    "Regensburg": ("DE", 49.013, 12.102, "Bayern"),
    "Garmisch-Partenkirchen": ("DE", 47.492, 11.095, "Bayern"),
    "Oberstdorf": ("DE", 47.410, 10.279, "Bayern"),
    "Köln": ("DE", 50.938, 6.960, "Nordrhein-Westfalen"),
    "Düsseldorf": ("DE", 51.228, 6.773, "Nordrhein-Westfalen"),
    "Münster": ("DE", 51.962, 7.626, "Nordrhein-Westfalen"),
    "Dortmund": ("DE", 51.514, 7.466, "Nordrhein-Westfalen"),
    "Bonn": ("DE", 50.737, 7.098, "Nordrhein-Westfalen"),
    "Frankfurt am Main": ("DE", 50.110, 8.682, "Hessen"),
    "Kassel": ("DE", 51.313, 9.479, "Hessen"),
    "Stuttgart": ("DE", 48.776, 9.182, "Baden-Württemberg"),
    "Freiburg": ("DE", 47.999, 7.842, "Baden-Württemberg"),
    "Karlsruhe": ("DE", 49.007, 8.404, "Baden-Württemberg"),
    "Konstanz": ("DE", 47.661, 9.175, "Baden-Württemberg"),
    "Heidelberg": ("DE", 49.399, 8.672, "Baden-Württemberg"),
    "Leipzig": ("DE", 51.340, 12.375, "Sachsen"),
    "Dresden": ("DE", 51.050, 13.738, "Sachsen"),
    "Hannover": ("DE", 52.375, 9.732, "Niedersachsen"),
    "Braunschweig": ("DE", 52.269, 10.526, "Niedersachsen"),
    "Bremen": ("DE", 53.079, 8.801, "Bremen"),
    "Kiel": ("DE", 54.323, 10.122, "Schleswig-Holstein"),
    "Lübeck": ("DE", 53.866, 10.687, "Schleswig-Holstein"),
    "Rostock": ("DE", 54.092, 12.099, "Mecklenburg-Vorpommern"),
    "Schwerin": ("DE", 53.629, 11.413, "Mecklenburg-Vorpommern"),
    "Erfurt": ("DE", 50.985, 11.030, "Thüringen"),
    "Jena": ("DE", 50.927, 11.586, "Thüringen"),
    "Magdeburg": ("DE", 52.131, 11.627, "Sachsen-Anhalt"),
    "Potsdam": ("DE", 52.391, 13.064, "Brandenburg"),
    "Mainz": ("DE", 49.993, 8.247, "Rheinland-Pfalz"),
    "Trier": ("DE", 49.750, 6.637, "Rheinland-Pfalz"),
    "Saarbrücken": ("DE", 49.240, 6.997, "Saarland"),
    # Austria
    "Wien": ("AT", 48.208, 16.373, "Wien"),
    "Graz": ("AT", 47.071, 15.439, "Steiermark"),
    "Salzburg": ("AT", 47.810, 13.055, "Salzburg"),
    "Innsbruck": ("AT", 47.269, 11.404, "Tirol"),
    "Linz": ("AT", 48.306, 14.286, "Oberösterreich"),
    "Klagenfurt": ("AT", 46.624, 14.305, "Kärnten"),
    # Switzerland
    "Zürich": ("CH", 47.377, 8.541, "Zürich"),
    "Bern": ("CH", 46.948, 7.447, "Bern"),
    "Basel": ("CH", 47.559, 7.588, "Basel-Stadt"),
    "Lausanne": ("CH", 46.520, 6.633, "Vaud"),
    "Luzern": ("CH", 47.050, 8.306, "Luzern"),
    "St. Gallen": ("CH", 47.424, 9.377, "St. Gallen"),
}
DE_CITIES = [c for c, v in CITIES.items() if v[0] == "DE"]
AT_CH_CITIES = [c for c, v in CITIES.items() if v[0] != "DE"]

WATER = {"Hamburg": "lake", "Kiel": "sea", "Rostock": "sea", "Lübeck": "sea", "Konstanz": "lake",
         "Köln": "river", "Düsseldorf": "river", "Mainz": "river", "Bonn": "river", "Wien": "river",
         "Regensburg": "river", "Dresden": "river", "Magdeburg": "river", "Basel": "river"}
MOUNTAIN = {"Garmisch-Partenkirchen", "Oberstdorf", "Innsbruck", "Salzburg", "Luzern", "Freiburg",
            "Klagenfurt", "St. Gallen", "Graz"}

OLY = {"swim_m": 1500, "bike_km": 40, "run_km": 10}
SPR = {"swim_m": 750, "bike_km": 20, "run_km": 5}
SSP = {"swim_m": 400, "bike_km": 10, "run_km": 2.5}
MID = {"swim_m": 1900, "bike_km": 90, "run_km": 21.1}
LONG = {"swim_m": 3800, "bike_km": 180, "run_km": 42.2}

STATES = ["open"] * 11 + ["not_open"] * 4 + ["waitlist"] * 2 + ["sold_out"] * 2 + ["closed"] + ["unknown"]


def iso(d: date, hour: int = 10, tz: str = "+01:00") -> str:
    return f"{d.isoformat()}T{hour:02d}:00:00{tz}"


def loc(city: str, with_coords: bool = True) -> dict:
    cc, lat, lon, region = CITIES[city]
    out = {"city": city, "region": region, "country": cc}
    if with_coords:
        out |= {"lat": lat, "lon": lon}
    return out


def random_date(start: date, end: date, weekend: bool = True) -> date:
    d = start + timedelta(days=rng.randint(0, (end - start).days))
    if weekend:
        d += timedelta(days=(6 - d.weekday()) % 7)  # next Sunday
    return d


def price_tiers(base: float, currency: str, race_day: date, state: str) -> list[dict]:
    """Early bird / regular / late tiers with validity windows ending before race day."""
    if state == "unknown" or rng.random() < 0.08:
        return []
    early_until = race_day - timedelta(days=120)
    regular_until = race_day - timedelta(days=21)
    tiers = [
        {"label": "Early bird", "amount": round(base * 0.85), "currency": currency,
         "valid_until": iso(early_until, 23)},
        {"label": "Regular", "amount": round(base), "currency": currency,
         "valid_from": iso(early_until, 23), "valid_until": iso(regular_until, 23)},
        {"label": "Late", "amount": round(base * 1.2), "currency": currency,
         "valid_from": iso(regular_until, 23)},
    ]
    if rng.random() < 0.3:
        tiers = tiers[1:2]  # single flat price
    return tiers


def registration(race_day: date, base_price: float, currency: str, url: str,
                 state: str | None = None) -> dict:
    state = state or rng.choice(STATES)
    opens = race_day - timedelta(days=rng.choice([150, 200, 270, 330]))
    closes = race_day - timedelta(days=rng.choice([3, 7, 10, 14]))
    if state == "not_open" and opens < TODAY:
        opens = TODAY + timedelta(days=rng.randint(7, 90))
    if state in ("open", "waitlist", "sold_out") and opens > TODAY:
        opens = TODAY - timedelta(days=rng.randint(5, 60))
    if state == "closed":
        closes = TODAY - timedelta(days=rng.randint(1, 30))
    return {
        "url": url,
        "opens_at": iso(opens),
        "closes_at": iso(closes, 23),
        "state": state,
        "prices": price_tiers(base_price, currency, race_day, state),
    }


def event(name: str, slug: str, sport: str, city: str, day: date, races: list[dict], *,
          platform: str = "raceresult", language: str = "de", with_coords: bool = True,
          website: bool = True, description: bool = True, status: str = "scheduled",
          end_day: date | None = None) -> dict:
    url = f"https://example.org/demo/{slug}"
    out = {
        "name": name, "sport_slug": sport, "start_date": day.isoformat(),
        "location": loc(city, with_coords), "organizer_name": ORG,
        "registration_url": url + "/register", "registration_platform": platform,
        "language": language, "source_url": url, "external_id": f"demo-{slug}-{day.year}",
        "races": races, "status": status,
    }
    if end_day:
        out["end_date"] = end_day.isoformat()
    if website:
        out["website"] = url
    if description:
        out["description"] = DEMO_NOTE
    return out


def currency_for(city: str) -> str:
    return "CHF" if CITIES[city][0] == "CH" else "EUR"


# ------------------------------------------------------------------ sport generators

TRI_NAMES = ["{city} Triathlon", "{feature} Triathlon {city}", "{city} City Triathlon",
             "Triathlon am {feature}", "{feature}-Triathlon"]
FEATURES = {"lake": ["See", "Stadtsee", "Baggersee", "Strandbad"], "river": ["Ufer", "Fluss", "Hafen"],
            "sea": ["Strand", "Ostsee", "Förde"]}


def make_triathlon(city: str, day: date, past: bool = False) -> dict:
    water = WATER.get(city, "lake")
    feature = rng.choice(FEATURES[water])
    name = rng.choice(TRI_NAMES).format(city=city, feature=feature)
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    profile = "mountain" if city in MOUNTAIN else rng.choice(["flat", "flat", "rolling", "hilly"])
    elev = {"flat": rng.randint(40, 200), "rolling": rng.randint(300, 600),
            "hilly": rng.randint(700, 1100), "mountain": rng.randint(1200, 2200)}[profile]
    wetsuit = rng.choice(["allowed", "allowed", "mandatory", "depends_on_temperature", "forbidden"])
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    kind = rng.choice(["short", "short", "middle", "long"])
    races = []
    attrs = {"wetsuit_rule": wetsuit, "water_type": water, "course_profile": profile,
             "surface": "road", "draft_legal": False, "elevation_gain_m": elev,
             "cutoff_minutes": None}

    def race(rname, dist, base, limit, disc=None, relay=False, cutoff=None):
        a = {k: v for k, v in attrs.items() if v is not None}
        if cutoff:
            a["cutoff_minutes"] = cutoff
        st = "closed" if past else None
        r = {"name": rname, "distances": dist, "attributes": a, "participant_limit": limit,
             "relay": relay, "registration": registration(day, base, cur, url, st)}
        if disc:
            r["discipline_slug"] = disc
        if r["registration"]["state"] in ("open", "waitlist", "sold_out") and limit:
            r["participants_registered"] = (limit if r["registration"]["state"] != "open"
                                            else rng.randint(int(limit * 0.2), int(limit * 0.9)))
        return r

    if kind == "short":
        races.append(race("Olympische Distanz", OLY, rng.choice([89, 95, 105, 115]),
                          rng.choice([800, 1200, 2000]), cutoff=210))
        races.append(race("Sprintdistanz", SPR, rng.choice([55, 65, 75]), rng.choice([500, 800, 1500])))
        if rng.random() < 0.5:
            races.append(race("Jedermann / Supersprint", SSP, 39, 400))
        if rng.random() < 0.4:
            races.append(race("Staffel Olympisch", OLY, 180, 100, disc="relay", relay=True))
    elif kind == "middle":
        races.append(race("Mitteldistanz", MID, rng.choice([179, 199, 229]), rng.choice([1000, 1800]),
                          cutoff=510))
        if rng.random() < 0.6:
            races.append(race("Olympische Distanz", OLY, 99, 1000))
    else:
        races.append(race("Langdistanz", LONG, rng.choice([490, 590, 650]), rng.choice([2000, 3000]),
                          cutoff=960))
        races.append(race("Mitteldistanz", MID, 249, 1500, cutoff=480))
        if rng.random() < 0.5:
            races.append(race("Langdistanz Staffel", LONG, 690, 150, disc="relay", relay=True))
    return event(name, slug, "triathlon", city, day, races,
                 platform=rng.choice(["raceresult", "raceresult", "datasport", "organizer"]),
                 with_coords=rng.random() > 0.08, website=rng.random() > 0.05,
                 description=rng.random() > 0.15)


RUN_NAMES = ["{city} Marathon", "{city} Halbmarathon", "{city} Stadtlauf", "{feature}lauf {city}",
             "{city} Citylauf", "{city} Frühlingslauf", "{city} Herbstlauf", "{city} Silvesterlauf"]
RUN_FEATURES = ["Altstadt", "Park", "Ufer", "Brücken", "Hafen", "Uni", "Firmen", "Nacht"]


def make_running(city: str, day: date, past: bool = False) -> dict:
    name = rng.choice(RUN_NAMES).format(city=city, feature=rng.choice(RUN_FEATURES))
    if "Silvester" in name:
        day = date(day.year, 12, 31)
    elif "Frühling" in name and day.month not in (3, 4, 5):
        day = random_date(date(2027, 3, 7), date(2027, 5, 30))
    elif "Herbst" in name and day.month not in (9, 10, 11):
        day = random_date(date(2027, 9, 5), date(2027, 11, 21))
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    profile = rng.choice(["flat", "flat", "flat", "rolling", "hilly"])
    certified = rng.random() < 0.7
    big = "Marathon" in name

    def race(rname, km, base, limit, elev):
        st = "closed" if past else None
        r = {"name": rname, "distances": {"run_km": km},
             "attributes": {"surface": "road", "course_profile": profile, "elevation_gain_m": elev,
                            "certified_course": certified},
             "participant_limit": limit, "registration": registration(day, base, cur, url, st)}
        if r["registration"]["state"] in ("open", "waitlist", "sold_out"):
            r["participants_registered"] = (limit if r["registration"]["state"] != "open"
                                            else rng.randint(int(limit * 0.2), int(limit * 0.9)))
        return r

    races = []
    if big:
        races.append(race("Marathon", 42.195, rng.choice([79, 99, 125, 150]),
                          rng.choice([5000, 12000, 25000, 40000]), rng.randint(40, 300)))
    if big or "Halbmarathon" in name or rng.random() < 0.6:
        races.append(race("Halbmarathon", 21.1, rng.choice([39, 49, 59, 75]),
                          rng.choice([3000, 8000, 15000]), rng.randint(20, 180)))
    races.append(race("10 km", 10, rng.choice([25, 32, 39, 45]), rng.choice([2000, 5000, 8000]),
                      rng.randint(10, 90)))
    if rng.random() < 0.7:
        races.append(race("5 km", 5, rng.choice([15, 19, 25]), rng.choice([1000, 3000]),
                          rng.randint(5, 40)))
    if rng.random() < 0.3:
        races.append(race("Staffelmarathon (4 × 10,5 km)", 42.195, 160, 400, rng.randint(40, 300))
                     | {"relay": True, "team": True})
    return event(name, slug, "running", city, day, races,
                 platform=rng.choice(["raceresult", "raceresult", "datasport", "organizer"]),
                 with_coords=rng.random() > 0.1, description=rng.random() > 0.2)


TRAIL_NAMES = ["{city} Trail", "{feature} Ultra Trail", "{feature} Skyrace", "{feature} Trailrun",
               "{feature} Höhenweg Trail"]
TRAIL_FEATURES = {"Garmisch-Partenkirchen": "Zugspitz", "Oberstdorf": "Allgäu", "Innsbruck": "Karwendel",
                  "Salzburg": "Untersberg", "Luzern": "Pilatus", "Freiburg": "Schwarzwald",
                  "Klagenfurt": "Kärnten", "St. Gallen": "Alpstein", "Graz": "Schöckl",
                  "Dresden": "Elbsandstein", "Jena": "Saale-Horizontale", "Trier": "Mosel",
                  "Kassel": "Habichtswald", "Heidelberg": "Odenwald", "Bonn": "Siebengebirge"}


def make_trail(city: str, day: date) -> dict:
    feature = TRAIL_FEATURES.get(city, city)
    name = rng.choice(TRAIL_NAMES).format(city=city, feature=feature)
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    alpine = city in MOUNTAIN
    races = []
    for rname, km, elev, base, limit in [
        ("Ultra " + str(rng.choice([65, 80, 100])) + " km", None, None, 165, 800),
        ("Trail " + str(rng.choice([35, 42, 45])) + " km", None, None, 95, 1200),
        ("Trail " + str(rng.choice([15, 18, 22])) + " km", None, None, 55, 1500),
    ]:
        km = float(rname.split()[1])
        elev = int(km * (rng.randint(45, 70) if alpine else rng.randint(18, 35)))
        if km > 60 and rng.random() < 0.3:
            continue
        r = {"name": rname, "distances": {"run_km": km, "elevation_gain_m": elev},
             "attributes": {"surface": "trail", "course_profile": "mountain" if alpine else "hilly",
                            "elevation_gain_m": elev, "certified_course": False,
                            "cutoff_minutes": int(km * (16 if alpine else 11))},
             "participant_limit": limit, "registration": registration(day, base, cur, url)}
        races.append(r)
    return event(name, slug, "trail-running", city, day, races, platform="organizer",
                 end_day=day + timedelta(days=1) if rng.random() < 0.4 else None)


def make_cycling(city: str, day: date) -> dict:
    kind = rng.choice(["gran-fondo", "gran-fondo", "gravel", "mtb-marathon", "road-race"])
    base_name = {"gran-fondo": "{city} Radmarathon", "gravel": "{city} Gravel Festival",
                 "mtb-marathon": "{feature} MTB Marathon", "road-race": "Rund um {city}"}[kind]
    name = base_name.format(city=city, feature=TRAIL_FEATURES.get(city, city))
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    alpine = city in MOUNTAIN
    surface = {"gran-fondo": "road", "road-race": "road", "gravel": "gravel", "mtb-marathon": "trail"}[kind]
    races = []
    for km in sorted(rng.sample([60, 85, 110, 140, 180, 220], 2 if rng.random() < 0.6 else 3)):
        elev = int(km * (rng.randint(18, 30) if alpine else rng.randint(6, 14)))
        races.append({"name": f"{km} km", "discipline_slug": kind,
                      "distances": {"bike_km": km, "elevation_gain_m": elev},
                      "attributes": {"surface": surface, "elevation_gain_m": elev,
                                     "course_profile": "mountain" if alpine else "hilly" if elev > 900 else "rolling",
                                     "draft_legal": kind in ("gran-fondo", "road-race")},
                      "participant_limit": rng.choice([500, 1500, 3000]),
                      "registration": registration(day, 45 + km * 0.4, cur, url)})
    return event(name, slug, "cycling", city, day, races,
                 platform=rng.choice(["raceresult", "datasport", "organizer"]))


def make_swim(city: str, day: date) -> dict:
    water = WATER.get(city, "lake")
    name = rng.choice(["{city} Open Water", "{city} Seeschwimmen", "{city} Langstreckenschwimmen",
                       "{city} Swim Challenge"]).format(city=city)
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    dists = sorted(rng.sample([1000, 2000, 3800, 5000, 10000, 15000, 26000], rng.choice([1, 2, 3])))
    races = [{"name": f"{m / 1000:g} km", "distances": {"swim_m": m},
              "attributes": {"water_type": water,
                             "wetsuit_rule": rng.choice(["allowed", "mandatory", "depends_on_temperature"]),
                             "cutoff_minutes": int(m / 1000 * 40)},
              "participant_limit": rng.choice([150, 300, 600]),
              "registration": registration(day, 35 + m / 150, cur, url)} for m in dists]
    return event(name, slug, "swimming", city, day, races, platform="organizer",
                 with_coords=rng.random() > 0.15)


def make_ocr(city: str, day: date) -> dict:
    name = rng.choice(["{city} Mud Masters", "{feature} Obstacle Race", "{city} Hindernislauf",
                       "Strong{city} OCR"]).format(city=city, feature=TRAIL_FEATURES.get(city, city))
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    races = [{"name": rname, "distances": {"run_km": km},
              "attributes": {"surface": "mixed", "course_profile": "hilly" if km > 10 else "rolling",
                             "elevation_gain_m": km * 30},
              "participant_limit": limit, "registration": registration(day, base, cur, url)}
             for rname, km, base, limit in [("Long Course 20 km", 20, 95, 2000),
                                            ("Standard 12 km", 12, 75, 4000),
                                            ("Short 6 km", 6, 49, 3000)]]
    if rng.random() < 0.5:
        races.pop(0)
    return event(name, slug, "ocr", city, day, races, platform="organizer", language="en",
                 end_day=day + timedelta(days=1))


def make_hyrox(city: str, day: date) -> dict:
    name = f"HYROX Arena Weekend {city}"
    slug = f"hyrox-arena-weekend-{city.lower().replace(' ', '-').replace('ü', 'ue')}"
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/tickets"
    races = []
    for rname, base, disc in [("Open", 109, "open"), ("Pro", 119, "pro"), ("Doubles", 199, "doubles"),
                              ("Relay", 279, "relay")]:
        st = rng.choice(["open", "open", "open", "sold_out", "waitlist", "not_open"])
        r = {"name": rname, "discipline_slug": disc, "distances": {"total_km": 8},
             "attributes": {"surface": "indoor"}, "team": disc in ("doubles", "relay"),
             "relay": disc == "relay", "participant_limit": 1500,
             "registration": registration(day, base, cur, url, st)}
        races.append(r)
    return event(name, slug, "hyrox", city, day, races, platform="organizer", language="en",
                 end_day=day + timedelta(days=1))


def make_hiking(city: str, day: date) -> dict:
    name = rng.choice(["{city} Megamarsch", "{feature} 24h-Wanderung", "{city} Mammutmarsch"]).format(
        city=city, feature=TRAIL_FEATURES.get(city, city))
    slug = name.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    cur = currency_for(city)
    url = f"https://example.org/demo/{slug}/register"
    races = [{"name": f"{km} km", "distances": {"run_km": km},
              "attributes": {"surface": "mixed", "course_profile": "rolling", "elevation_gain_m": km * 8,
                             "cutoff_minutes": km * 14},
              "participant_limit": 2500, "registration": registration(day, 39 + km * 0.4, cur, url)}
             for km in rng.choice([[50, 100], [30, 60], [100]])]
    return event(name, slug, "hiking", city, day, races, platform="organizer",
                 end_day=day + timedelta(days=1))


# ------------------------------------------------------------------ assemble

events: list[dict] = []
season_start, season_end = date(2026, 11, 1), date(2027, 12, 31)
shuffled_de = DE_CITIES[:]
rng.shuffle(shuffled_de)

# Triathlon: 22 (18 DE + 4 AT/CH), season April–September
for city in shuffled_de[:18] + rng.sample(AT_CH_CITIES, 4):
    events.append(make_triathlon(city, random_date(date(2027, 4, 11), date(2027, 9, 26))))

# Running: 26 (22 DE + 4 AT/CH), all year
rng.shuffle(shuffled_de)
for city in shuffled_de[:22] + rng.sample(AT_CH_CITIES, 4):
    events.append(make_running(city, random_date(season_start, season_end)))

# Trail: 10 — alpine/hilly cities
for city in rng.sample(list(TRAIL_FEATURES), 10):
    events.append(make_trail(city, random_date(date(2027, 5, 1), date(2027, 10, 17))))

# Cycling: 8
for city in rng.sample(DE_CITIES, 6) + rng.sample(AT_CH_CITIES, 2):
    events.append(make_cycling(city, random_date(date(2027, 5, 1), date(2027, 9, 19))))

# Swimming: 6 — cities with water
for city in rng.sample([c for c in WATER if c in CITIES], 6):
    events.append(make_swim(city, random_date(date(2027, 6, 13), date(2027, 8, 29))))

# OCR: 5, HYROX: 6 (incl. two in the next weeks), hiking: 5
for city in rng.sample(DE_CITIES, 5):
    events.append(make_ocr(city, random_date(date(2027, 5, 1), date(2027, 10, 3))))
for city, day in [("Hamburg", date(2026, 11, 14)), ("Berlin", date(2026, 12, 5)), ("Wien", date(2027, 2, 6)),
                  ("Köln", date(2027, 3, 13)), ("Zürich", date(2027, 4, 17)), ("München", date(2027, 10, 9))]:
    events.append(make_hyrox(city, day))
for city in rng.sample(DE_CITIES, 5):
    events.append(make_hiking(city, random_date(date(2027, 4, 25), date(2027, 9, 12))))

# Past 2026 editions for ~15 events (same name → same event, extra edition with status finished)
past_pool = [e for e in events if e["sport_slug"] in ("triathlon", "running")]
for e in rng.sample(past_pool, 15):
    d = date.fromisoformat(e["start_date"])
    past_day = date(2026, d.month, min(d.day, 28)) - timedelta(days=rng.choice([0, 7]))
    if past_day >= TODAY:
        past_day = past_day.replace(year=2026, month=max(1, d.month - 6))
    past = json.loads(json.dumps(e))
    past["start_date"] = past_day.isoformat()
    past.pop("end_date", None)
    past["status"] = "finished"
    past["external_id"] = past["external_id"].rsplit("-", 1)[0] + f"-{past_day.year}"
    for r in past["races"]:
        r["registration"]["state"] = "closed"
        r["registration"]["opens_at"] = iso(past_day - timedelta(days=200))
        r["registration"]["closes_at"] = iso(past_day - timedelta(days=7), 23)
        r["registration"]["prices"] = r["registration"]["prices"][-1:]
        r["participants_registered"] = r.get("participant_limit")
    events.append(past)

# A few cancelled / postponed editions
for e in rng.sample([e for e in events if e["status"] == "scheduled"], 3):
    e["status"] = rng.choice(["cancelled", "postponed"])
    for r in e["races"]:
        r["registration"]["state"] = "closed"
        r["registration"]["prices"] = []

# One event with almost no data (tests completeness score / "unknown" badge)
events.append(event("Kleiner Dorflauf Musterhausen", "dorflauf-musterhausen", "running", "Erfurt",
                    date(2027, 6, 6), [{"name": "Volkslauf", "distances": {},
                                        "attributes": {}}],
                    platform="organizer", with_coords=False, website=False, description=False))

events.sort(key=lambda e: (e["start_date"], e["name"]))
out = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sample_events.json"
out.write_text(json.dumps(events, ensure_ascii=False, indent=1))
by_sport: dict[str, int] = {}
for e in events:
    by_sport[e["sport_slug"]] = by_sport.get(e["sport_slug"], 0) + 1
print(f"wrote {len(events)} demo editions to {out}")
print(" ", by_sport)
print("  generated at", datetime.now().isoformat(timespec="seconds"))
