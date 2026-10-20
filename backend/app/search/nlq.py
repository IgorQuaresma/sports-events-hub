"""Natural-language query → SearchFilters.

Rules first (fast, free, deterministic, works offline). When an Anthropic API key is configured
the LLM path is tried first and the rules act as fallback. Either way the UI shows the parsed
filters as chips so the user can see and correct what was understood.
"""

from __future__ import annotations

import re
from datetime import date

from app.schemas.search import AttributeFilter, SearchFilters

# ---------------------------------------------------------------- vocabularies (DE + EN)

SPORT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(triathlon|triathlons|tri)\b", "triathlon"),
    (r"\b(hyrox)\b", "hyrox"),
    (r"\b(trail ?run\w*|trail|ultratrail|ultra-trail)\b", "trail-running"),
    (r"\b(ocr|obstacle|hindernis\w*|spartan|tough mudder|strong ?viking)\b", "ocr"),
    (
        r"\b(radmarathon|gran ?fondo|gravel|mtb|rennrad|cycling|bike race|radrennen|velo)\b",
        "cycling",
    ),
    (r"\b(swim\w*|schwimm\w*|freiwasser|open ?water)\b", "swimming"),
    (r"\b(wander\w*|hik\w*|megamarsch|mammutmarsch)\b", "hiking"),
    (
        r"\b(marathon|halbmarathon|half ?marathon|lauf|laufen|run|running|10k|5k|10 ?km|5 ?km|ultra\w*)\b",
        "running",
    ),
]

DISCIPLINE_PATTERNS: list[tuple[str, str, str]] = [  # (regex, sport, discipline)
    (r"\b(olympic|olympisch\w*|kurzdistanz|od)\b", "triathlon", "olympic"),
    (r"\b(super ?sprint)\b", "triathlon", "super-sprint"),
    (r"\b(sprint\w*)\b", "triathlon", "sprint"),
    (
        r"\b(mitteldistanz|70\.3|half ?ironman|middle distance|halbe? ?ironman)\b",
        "triathlon",
        "middle",
    ),
    (r"\b(langdistanz|ironman|long distance|full distance|140\.6)\b", "triathlon", "long"),
    (r"\b(halbmarathon|half ?marathon|21k|21,1|21\.1)\b", "running", "half-marathon"),
    (r"\b(marathon)\b", "running", "marathon"),
    (r"\b(10 ?k|10 ?km|zehner)\b", "running", "10k"),
    (r"\b(5 ?k|5 ?km|parkrun)\b", "running", "5k"),
    (r"\b(ultra ?trail|ultratrail)\b", "trail-running", "ultra-trail"),
    (r"\b(ultra\w*)\b", "running", "ultra"),
    (r"\b(gran ?fondo|radmarathon)\b", "cycling", "gran-fondo"),
    (r"\b(gravel)\b", "cycling", "gravel"),
    (r"\b(mtb|mountainbike)\b", "cycling", "mtb-marathon"),
    (r"\b(open ?water|freiwasser)\b", "swimming", "open-water"),
    (r"\b(doubles)\b", "hyrox", "doubles"),
    (r"\b(pro)\b", "hyrox", "pro"),
]

COUNTRY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(germany|deutschland|german|deutsch\w*)\b", "DE"),
    (r"\b(austria|österreich|oesterreich|austrian)\b", "AT"),
    (r"\b(switzerland|schweiz|swiss|suisse)\b", "CH"),
    (r"\b(dach)\b", "DE,AT,CH"),
]

MONTHS: dict[str, int] = {
    "januar": 1,
    "january": 1,
    "jan": 1,
    "februar": 2,
    "february": 2,
    "feb": 2,
    "märz": 3,
    "maerz": 3,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "juni": 6,
    "june": 6,
    "jun": 6,
    "juli": 7,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "october": 10,
    "oct": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "december": 12,
    "dez": 12,
    "dec": 12,
}

SEASONS = {
    "frühling": (3, 5),
    "fruehling": (3, 5),
    "spring": (3, 5),
    "sommer": (6, 8),
    "summer": (6, 8),
    "herbst": (9, 11),
    "autumn": (9, 11),
    "fall": (9, 11),
    "winter": (12, 2),
}

CITIES: dict[str, tuple[float, float, str]] = {
    "berlin": (52.52, 13.405, "DE"),
    "hamburg": (53.551, 9.994, "DE"),
    "münchen": (48.137, 11.575, "DE"),
    "munich": (48.137, 11.575, "DE"),
    "köln": (50.938, 6.96, "DE"),
    "cologne": (50.938, 6.96, "DE"),
    "frankfurt": (50.11, 8.682, "DE"),
    "stuttgart": (48.776, 9.182, "DE"),
    "düsseldorf": (51.228, 6.773, "DE"),
    "leipzig": (51.34, 12.375, "DE"),
    "dresden": (51.05, 13.738, "DE"),
    "hannover": (52.375, 9.732, "DE"),
    "nürnberg": (49.453, 11.077, "DE"),
    "bremen": (53.079, 8.801, "DE"),
    "münster": (51.962, 7.626, "DE"),
    "freiburg": (47.999, 7.842, "DE"),
    "karlsruhe": (49.007, 8.404, "DE"),
    "dortmund": (51.514, 7.466, "DE"),
    "wien": (48.208, 16.373, "AT"),
    "vienna": (48.208, 16.373, "AT"),
    "graz": (47.071, 15.439, "AT"),
    "salzburg": (47.81, 13.055, "AT"),
    "innsbruck": (47.269, 11.404, "AT"),
    "linz": (48.306, 14.286, "AT"),
    "zürich": (47.377, 8.541, "CH"),
    "zurich": (47.377, 8.541, "CH"),
    "bern": (46.948, 7.447, "CH"),
    "basel": (47.559, 7.588, "CH"),
    "genf": (46.204, 6.143, "CH"),
    "geneva": (46.204, 6.143, "CH"),
    "lausanne": (46.52, 6.633, "CH"),
    "luzern": (47.05, 8.306, "CH"),
}

ATTRIBUTE_PATTERNS: list[tuple[str, AttributeFilter, str]] = [
    (
        r"\b(no wetsuit|ohne neopren|neoprenverbot|wetsuit forbidden|wetsuit[- ]free)\b",
        AttributeFilter(key="wetsuit_rule", op="eq", value="forbidden"),
        "no wetsuit",
    ),
    (
        r"\b(wetsuit|neopren\w*)\b",
        AttributeFilter(key="wetsuit_rule", op="in", value=["allowed", "mandatory"]),
        "wetsuit allowed",
    ),
    (
        r"\b(flat|flach\w*|schnell\w*|fast course|pb course)\b",
        AttributeFilter(key="course_profile", op="eq", value="flat"),
        "flat course",
    ),
    (
        r"\b(hilly|hügelig|huegelig|bergig|mountain\w*|alpine?)\b",
        AttributeFilter(key="course_profile", op="in", value=["hilly", "mountain"]),
        "hilly course",
    ),
    (
        r"\b(draft ?legal|windschatten)\b",
        AttributeFilter(key="draft_legal", op="eq", value=True),
        "draft legal",
    ),
    (
        r"\b(certified|vermessen\w*|aims|dlv-vermessen)\b",
        AttributeFilter(key="certified_course", op="eq", value=True),
        "certified course",
    ),
    (r"\b(lake|see)\b", AttributeFilter(key="water_type", op="eq", value="lake"), "lake swim"),
    (r"\b(sea|meer|ocean)\b", AttributeFilter(key="water_type", op="eq", value="sea"), "sea swim"),
]

STOP_WORDS = set(
    "in im am an auf mit und oder für fuer der die das den dem ein eine einen einer von vom zum zur "
    "the a an and or for of to with at on near by around nearby distance distanz events event "
    "rennen race races wettkampf veranstaltung veranstaltungen suche suchen find finde search "
    "ich i want möchte will um bei nähe naehe within km anmeldung registration open offen "
    "allowed erlaubt mandatory pflicht forbidden verboten course strecke rule regel ok possible "
    "möglich moeglich please bitte some any ein paar nächste next".split()
)


def _strip(text: str, pattern: str) -> str:
    return re.sub(pattern, " ", text, flags=re.IGNORECASE)


def parse_rules(query: str) -> tuple[SearchFilters, list[str]]:
    q = query.lower().strip()
    chips: list[str] = []
    f = SearchFilters()
    rest = q

    # disciplines first (more specific), they imply a sport
    for pat, sport, disc in DISCIPLINE_PATTERNS:
        if re.search(pat, rest, re.IGNORECASE):
            if disc not in f.discipline:
                f.discipline.append(disc)
            if sport not in f.sport:
                f.sport.append(sport)
            chips.append(f"{sport} · {disc}")
            rest = _strip(rest, pat)
    for pat, sport in SPORT_PATTERNS:
        if re.search(pat, rest, re.IGNORECASE):
            if sport not in f.sport:
                f.sport.append(sport)
                chips.append(sport)
            rest = _strip(rest, pat)

    for pat, code in COUNTRY_PATTERNS:
        if re.search(pat, rest, re.IGNORECASE):
            for c in code.split(","):
                if c not in f.country:
                    f.country.append(c)
            chips.append(code)
            rest = _strip(rest, pat)

    # near <city> / city mention
    for city, (lat, lon, _cc) in CITIES.items():
        if re.search(rf"\b{re.escape(city)}\b", rest):
            f.near_lat, f.near_lon = lat, lon
            m = re.search(r"(\d{2,3})\s*km", rest)
            f.radius_km = float(m.group(1)) if m else 75.0
            chips.append(f"near {city.title()} ({int(f.radius_km)} km)")
            rest = _strip(rest, rf"\b{re.escape(city)}\b")
            if m:
                rest = _strip(rest, re.escape(m.group(0)))
            break

    # dates: explicit year, month names, seasons
    today = date.today()
    year_m = re.search(r"\b(20\d{2})\b", rest)
    year = int(year_m.group(1)) if year_m else None
    if year_m:
        rest = _strip(rest, r"\b20\d{2}\b")
    months_found = [MONTHS[m] for m in re.findall(r"\b([a-zäöü]+)\b", rest) if m in MONTHS]
    season = next((s for s in SEASONS if re.search(rf"\b{s}\b", rest)), None)
    if months_found:
        mo = months_found[0]
        y = year or (today.year if mo >= today.month else today.year + 1)
        f.date_from = date(y, mo, 1)
        f.date_to = date(y + (mo == 12), (mo % 12) + 1, 1)
        chips.append(f"{f.date_from:%B %Y}")
        for name, num in MONTHS.items():
            if num == mo:
                rest = _strip(rest, rf"\b{name}\b")
    elif season:
        a, b = SEASONS[season]
        y = year or (today.year if a >= today.month else today.year + 1)
        f.date_from = date(y, a, 1)
        f.date_to = date(y + 1, 1, 1) if b < a else date(y + (b == 12), (b % 12) + 1, 1)
        chips.append(f"{season} {y}")
        rest = _strip(rest, rf"\b{season}\b")
    elif year:
        f.date_from = max(date(year, 1, 1), today)
        f.date_to = date(year + 1, 1, 1)
        chips.append(str(year))

    for pat, attr, label in ATTRIBUTE_PATTERNS:
        if re.search(pat, rest, re.IGNORECASE):
            f.attributes.append(attr)
            chips.append(label)
            rest = _strip(rest, pat)

    if re.search(
        r"\b(anmeldung (offen|möglich)|registration open|open registration|anmelden)\b", rest
    ):
        f.reg_state = ["open"]
        chips.append("registration open")
        rest = _strip(
            rest, r"\b(anmeldung (offen|möglich)|registration open|open registration|anmelden)\b"
        )

    if re.search(r"\b(staffel|relay)\b", rest):
        f.relay = True
        chips.append("relay")
        rest = _strip(rest, r"\b(staffel|relay)\b")

    m = re.search(r"(?:unter|under|max\.?|bis|<)\s*(\d{2,4})\s*(?:€|eur|euro|chf)?", rest)
    if m:
        f.price_max = float(m.group(1))
        chips.append(f"≤ {int(f.price_max)} €")
        rest = _strip(rest, re.escape(m.group(0)))

    leftover = [w for w in re.findall(r"[a-zäöüß0-9\-\.]{2,}", rest) if w not in STOP_WORDS]
    if leftover:
        f.q = " ".join(leftover)
        chips.append(f"“{f.q}”")
    return f, chips


async def parse_query(query: str) -> tuple[SearchFilters, list[str], str]:
    """Return (filters, chips, method). Tries the LLM when configured, else rules."""
    from app.ai.gateway import llm_available, parse_query_llm

    if llm_available():
        try:
            f, chips = await parse_query_llm(query)
            return f, chips, "llm"
        except Exception:  # noqa: BLE001 — any LLM failure falls back to rules
            pass
    f, chips = parse_rules(query)
    return f, chips, "rules"
