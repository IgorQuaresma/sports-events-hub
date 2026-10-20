"""Data-driven sport taxonomy. Seeded into the DB by `app.cli seed`; editable afterwards."""

SPORTS: list[dict] = [
    {"slug": "triathlon", "name": {"de": "Triathlon", "en": "Triathlon"}},
    {"slug": "running", "name": {"de": "Laufen", "en": "Running"}},
    {"slug": "trail-running", "name": {"de": "Trailrunning", "en": "Trail running"}},
    {"slug": "cycling", "name": {"de": "Radsport", "en": "Cycling"}},
    {"slug": "swimming", "name": {"de": "Schwimmen", "en": "Swimming"}},
    {"slug": "ocr", "name": {"de": "Hindernislauf (OCR)", "en": "Obstacle course racing"}},
    {"slug": "hyrox", "name": {"de": "HYROX", "en": "HYROX"}},
    {"slug": "hiking", "name": {"de": "Wandern / Fernwanderung", "en": "Hiking events"}},
]

# (sport, slug, name_de, name_en, canonical distances)
DISCIPLINES: list[tuple[str, str, str, str, dict | None]] = [
    (
        "triathlon",
        "super-sprint",
        "Supersprint",
        "Super sprint",
        {"swim_m": 400, "bike_km": 10, "run_km": 2.5},
    ),
    (
        "triathlon",
        "sprint",
        "Sprintdistanz",
        "Sprint distance",
        {"swim_m": 750, "bike_km": 20, "run_km": 5},
    ),
    (
        "triathlon",
        "olympic",
        "Olympische Distanz",
        "Olympic distance",
        {"swim_m": 1500, "bike_km": 40, "run_km": 10},
    ),
    (
        "triathlon",
        "middle",
        "Mitteldistanz (70.3)",
        "Middle distance (70.3)",
        {"swim_m": 1900, "bike_km": 90, "run_km": 21.1},
    ),
    (
        "triathlon",
        "long",
        "Langdistanz (Ironman)",
        "Long distance (Ironman)",
        {"swim_m": 3800, "bike_km": 180, "run_km": 42.2},
    ),
    ("triathlon", "relay", "Staffel", "Relay", None),
    ("triathlon", "other", "Sonstige / Volksdistanz", "Other / popular distance", None),
    ("running", "5k", "5 km", "5K", {"run_km": 5}),
    ("running", "10k", "10 km", "10K", {"run_km": 10}),
    ("running", "half-marathon", "Halbmarathon", "Half marathon", {"run_km": 21.1}),
    ("running", "marathon", "Marathon", "Marathon", {"run_km": 42.2}),
    ("running", "ultra", "Ultralauf", "Ultra", None),
    ("running", "other", "Sonstige Laufdistanz", "Other distance", None),
    ("trail-running", "short-trail", "Kurztrail (< 25 km)", "Short trail (< 25 km)", None),
    ("trail-running", "trail-marathon", "Trail-Marathon (25-45 km)", "Trail marathon", None),
    ("trail-running", "ultra-trail", "Ultratrail (> 45 km)", "Ultra trail (> 45 km)", None),
    ("cycling", "road-race", "Straßenrennen (Jedermann)", "Road race", None),
    ("cycling", "gran-fondo", "Radmarathon / Gran Fondo", "Gran fondo", None),
    ("cycling", "gravel", "Gravel", "Gravel", None),
    ("cycling", "mtb-marathon", "MTB-Marathon", "MTB marathon", None),
    ("cycling", "time-trial", "Zeitfahren", "Time trial", None),
    ("swimming", "open-water", "Freiwasser (bis 5 km)", "Open water (up to 5 km)", None),
    ("swimming", "marathon-swim", "Marathonschwimmen (5-25 km)", "Marathon swim", None),
    ("swimming", "ultra-swim", "Ultraschwimmen (> 25 km)", "Ultra swim (> 25 km)", None),
    ("ocr", "short", "Kurzstrecke (< 10 km)", "Short course (< 10 km)", None),
    ("ocr", "standard", "Standard (10-15 km)", "Standard (10-15 km)", None),
    ("ocr", "long", "Langstrecke (> 15 km)", "Long course (> 15 km)", None),
    ("hyrox", "open", "HYROX Open", "HYROX Open", None),
    ("hyrox", "pro", "HYROX Pro", "HYROX Pro", None),
    ("hyrox", "doubles", "HYROX Doubles", "HYROX Doubles", None),
    ("hyrox", "relay", "HYROX Relay", "HYROX Relay", None),
    ("hiking", "day-hike", "Tageswanderung", "Day hike", None),
    ("hiking", "mega-march", "Megamarsch / 24h", "Mega march / 24 h", None),
]

# Attribute keys shown as filters in the UI; values are free but these are the known ones.
ATTRIBUTE_KEYS: dict[str, dict] = {
    "wetsuit_rule": {
        "label": {"de": "Neopren", "en": "Wetsuit"},
        "values": ["allowed", "mandatory", "forbidden", "depends_on_temperature"],
    },
    "surface": {
        "label": {"de": "Untergrund", "en": "Surface"},
        "values": ["road", "trail", "mixed", "track", "gravel"],
    },
    "course_profile": {
        "label": {"de": "Profil", "en": "Course profile"},
        "values": ["flat", "rolling", "hilly", "mountain"],
    },
    "water_type": {
        "label": {"de": "Gewässer", "en": "Water type"},
        "values": ["lake", "river", "sea", "pool"],
    },
    "draft_legal": {
        "label": {"de": "Windschatten erlaubt", "en": "Draft legal"},
        "values": [True, False],
    },
    "elevation_gain_m": {
        "label": {"de": "Höhenmeter", "en": "Elevation gain (m)"},
        "numeric": True,
    },
    "cutoff_minutes": {"label": {"de": "Zeitlimit (min)", "en": "Cut-off (min)"}, "numeric": True},
    "certified_course": {
        "label": {"de": "Vermessene Strecke", "en": "Certified course"},
        "values": [True, False],
    },
}

COUNTRIES = {"DE": "Deutschland", "AT": "Österreich", "CH": "Schweiz"}
