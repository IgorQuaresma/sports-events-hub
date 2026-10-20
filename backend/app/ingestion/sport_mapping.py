"""Map free-text titles / provider categories onto the sport taxonomy (de + en keywords).

Used by connectors whose sources mix many sports (RunSignup, Ticketmaster, Wikidata).
Order matters: the most specific sport wins ("Trail-Halbmarathon" → trail-running, not running).
"""

from __future__ import annotations

import re

_SPORT_PATTERNS: list[tuple[str, str]] = [
    ("hyrox", r"\bhyrox\b"),
    (
        "ocr",
        r"\b(ocr|obstacle|hindernis\w*|spartan|tough\s*mudder|strong\s*viking|xletix|mud\s*run)\b",
    ),
    ("triathlon", r"\b(triathlon|duathlon|ironman|70\.3|aquathlon|swimrun|cross\s*tri\w*)\b"),
    ("trail-running", r"\b(trail\w*|berglauf|skyrace|sky\s*run\w*|ultra[-\s]?trail|vertical)\b"),
    (
        "swimming",
        r"\b(open[-\s]?water|freiwasser|schwimm\w*|swim\w*|seeüberquerung|seequerung)\b",
    ),
    (
        "cycling",
        r"\b(rad(rennen|sport|tour|fahr\w*|klassiker)|cycl\w*|bike|gravel|gran\s*fondo|mtb|mountainbike|velo\w*|jedermann\w*|"
        r"radmarathon|zeitfahren|criterium)\b",
    ),
    ("hiking", r"\b(wander\w*|hike|hiking|megamarsch|mammutmarsch|fernmarsch|100\s*km\s*marsch)\b"),
    (
        "running",
        r"\b(marathon|halbmarathon|half[-\s]?marathon|lauf\w*|run\w*|10\s?k|5\s?k|"
        r"stadtlauf|volkslauf|silvesterlauf|crosslauf)\b",
    ),
]
_COMPILED = [(sport, re.compile(p, re.IGNORECASE)) for sport, p in _SPORT_PATTERNS]


def sport_from_text(*texts: str | None) -> str | None:
    """First taxonomy sport whose keywords appear in any of `texts`, else None."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    for sport, rx in _COMPILED:
        if rx.search(blob):
            return sport
    return None


# RunSignup `event_type` → taxonomy sport (None = not an endurance race we list)
RUNSIGNUP_EVENT_TYPES: dict[str, str | None] = {
    "running_race": "running",
    "running_only": "running",
    "walking_only": "hiking",
    "race_walk": "running",
    "wheelchair": "running",
    "triathlon": "triathlon",
    "duathlon": "triathlon",
    "aqua_bike": "triathlon",
    "swim_run": "triathlon",
    "bike_race": "cycling",
    "bike_ride": "cycling",
    "mountain_bike_race": "cycling",
    "gravel_grinder": "cycling",
    "fundraising_ride": "cycling",
    "trail_race": "trail-running",
    "open_course_trail": "trail-running",
    "ultra": "running",
    "hike": "hiking",
    "ruck": "hiking",
    "obstacle_course": "ocr",
    "adventure_race": "ocr",
    "swim": "swimming",
    "virtual_race": None,
    "nonprofit_event": None,
    "ski": None,
    "paddle_sports": None,
    "disc_golf": None,
    "clinic": None,
    "expo": None,
    "skate": None,
    "other": None,
}
