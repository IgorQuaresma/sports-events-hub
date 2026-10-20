"""Entity resolution: does an incoming candidate describe an edition we already have?

Blocking: same sport, start date within ±3 days. Scoring: name similarity (year/sport words
removed), city agreement, registration-URL domain agreement. ≥ 0.85 → same edition.
Below that we create a new one; a review queue for the grey zone is planned (plan §4.2).
"""

from __future__ import annotations

import re
from datetime import timedelta
from difflib import SequenceMatcher
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, EventEdition, Sport
from app.schemas.candidate import EventCandidate

MERGE_THRESHOLD = 0.85

_NOISE = re.compile(
    r"\b(20\d{2}|triathlon|marathon|lauf|run|race|city|stadt|der|die|das|the|e\.?v\.?|gmbh|"
    r"halbmarathon|half|edition|\d+\.)\b",
    re.IGNORECASE,
)


def canonical_name(name: str) -> str:
    s = _NOISE.sub(" ", name.lower())
    s = re.sub(r"[^a-zäöüß0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str, b: str) -> float:
    ca, cb = canonical_name(a), canonical_name(b)
    if not ca or not cb:
        return 0.0
    ratio = SequenceMatcher(None, ca, cb).ratio()
    ta, tb = set(ca.split()), set(cb.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return max(ratio, jaccard)


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(str(url)).hostname or ""
    return host.removeprefix("www.") or None


def score_pair(c: EventCandidate, ed: EventEdition) -> float:
    s_name = name_similarity(c.name, ed.event.name)
    city_c = (c.location.city or "").lower()
    city_e = (ed.venue.city if ed.venue else "") or ""
    if city_c and city_e:
        s_city = 1.0 if city_c == city_e.lower() else 0.0
    else:
        s_city = 0.6  # unknown: mildly positive
    score = 0.75 * s_name + 0.25 * s_city
    if _domain(c.registration_url) and _domain(c.registration_url) == _domain(ed.registration_url):
        score = min(1.0, score + 0.15)
    return score


async def find_existing_edition(session: AsyncSession, c: EventCandidate) -> EventEdition | None:
    stmt = (
        select(EventEdition)
        .join(Event)
        .join(Sport)
        .where(
            Sport.slug == c.sport_slug,
            EventEdition.start_date.between(
                c.start_date - timedelta(days=3), c.start_date + timedelta(days=3)
            ),
        )
        .options(selectinload(EventEdition.event), selectinload(EventEdition.venue))
    )
    candidates = (await session.execute(stmt)).scalars().all()
    best: tuple[float, EventEdition | None] = (0.0, None)
    for ed in candidates:
        s = score_pair(c, ed)
        if s > best[0]:
            best = (s, ed)
    return best[1] if best[0] >= MERGE_THRESHOLD else None
