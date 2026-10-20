from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import pseudonymous_client_hash
from app.models import Event, EventEdition, OutboundClick, Race, RegistrationWindow, SourceRecord
from app.schemas.events import (
    EditionOut,
    EditionSummaryOut,
    EventOut,
    PriceTierOut,
    ProvenanceOut,
    RaceOut,
    RegistrationWindowOut,
    VenueOut,
)

router = APIRouter(tags=["events"])

_EDITION_LOAD = (
    selectinload(EventEdition.venue),
    selectinload(EventEdition.races).selectinload(Race.discipline),
    selectinload(EventEdition.races).selectinload(Race.attributes),
    selectinload(EventEdition.races)
    .selectinload(Race.registration_windows)
    .selectinload(RegistrationWindow.price_tiers),
    selectinload(EventEdition.source_records).selectinload(SourceRecord.source),
)


def _edition_out(ed: EventEdition, lang: str = "de") -> EditionOut:
    races: list[RaceOut] = []
    for r in ed.races:
        window = max(r.registration_windows, key=lambda w: w.state_checked_at, default=None)
        races.append(
            RaceOut(
                id=r.id,
                name=r.name,
                discipline_slug=r.discipline.slug,
                start_time=r.start_time,
                distances=r.distances or {},
                attributes={a.key: a.value for a in r.attributes},
                participant_limit=r.participant_limit,
                participants_registered=r.participants_registered,
                relay=r.relay,
                team=r.team,
                registration=(
                    RegistrationWindowOut(
                        state=window.state,
                        opens_at=window.opens_at,
                        closes_at=window.closes_at,
                        state_checked_at=window.state_checked_at,
                        url=window.url,
                        price_tiers=[
                            PriceTierOut(
                                label=t.label,
                                amount=t.amount,
                                currency=t.currency,
                                valid_from=t.valid_from,
                                valid_until=t.valid_until,
                            )
                            for t in window.price_tiers
                        ],
                    )
                    if window
                    else None
                ),
            )
        )
    summary = None
    if ed.summary_i18n:
        summary = ed.summary_i18n.get(lang) or next(iter(ed.summary_i18n.values()), None)
    return EditionOut(
        id=ed.id,
        year=ed.year,
        start_date=ed.start_date,
        end_date=ed.end_date,
        status=ed.status,
        venue=(
            VenueOut(
                name=ed.venue.name,
                street=ed.venue.street,
                postal_code=ed.venue.postal_code,
                city=ed.venue.city,
                region=ed.venue.region,
                country=ed.venue.country,
                lat=ed.venue.lat,
                lon=ed.venue.lon,
            )
            if ed.venue
            else None
        ),
        registration_url=ed.registration_url,
        info_url=ed.info_url,
        registration_platform=ed.registration_platform,
        summary=summary,
        data_quality_score=ed.data_quality_score,
        last_verified_at=ed.last_verified_at,
        races=races,
        provenance=[
            ProvenanceOut(
                source_key=sr.source.key,
                source_name=sr.source.name,
                source_kind=sr.source.kind,
                url=sr.url,
                fetched_at=sr.fetched_at,
                parse_method=sr.parse_method,
                parse_confidence=sr.parse_confidence,
            )
            for sr in sorted(ed.source_records, key=lambda s: s.fetched_at, reverse=True)[:5]
        ],
    )


@router.get("/events/{slug}", response_model=EventOut)
async def get_event(
    slug: str, session: Annotated[AsyncSession, Depends(get_session)], lang: str = "de"
) -> EventOut:
    stmt = (
        select(Event)
        .where(Event.slug == slug, Event.status == "published")
        .options(
            selectinload(Event.sport),
            selectinload(Event.organizer),
            selectinload(Event.editions).options(*_EDITION_LOAD),
        )
    )
    ev = (await session.execute(stmt)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "event not found")
    today = date.today()
    upcoming = [e for e in ev.editions if e.start_date >= today and e.status != "cancelled"]
    next_ed = (
        min(upcoming, key=lambda e: e.start_date)
        if upcoming
        else (max(ev.editions, key=lambda e: e.start_date) if ev.editions else None)
    )
    desc = None
    if ev.description_i18n:
        desc = ev.description_i18n.get(lang) or next(iter(ev.description_i18n.values()), None)
    return EventOut(
        id=ev.id,
        slug=ev.slug,
        name=ev.name,
        sport_slug=ev.sport.slug,
        website=ev.website,
        organizer_name=ev.organizer.name if ev.organizer else None,
        description=desc,
        editions=[
            EditionSummaryOut(
                id=e.id,
                year=e.year,
                start_date=e.start_date,
                status=e.status,
                city=e.venue.city if e.venue else None,
                country=e.venue.country if e.venue else None,
            )
            for e in ev.editions
        ],
        next_edition=_edition_out(next_ed, lang) if next_ed else None,
        is_demo=bool(next_ed)
        and bool(next_ed.source_records)
        and all(sr.source.key == "sample" for sr in next_ed.source_records),
    )


@router.get("/editions/{edition_id}", response_model=EditionOut)
async def get_edition(
    edition_id: UUID, session: Annotated[AsyncSession, Depends(get_session)], lang: str = "de"
) -> EditionOut:
    stmt = select(EventEdition).where(EventEdition.id == edition_id).options(*_EDITION_LOAD)
    ed = (await session.execute(stmt)).scalar_one_or_none()
    if ed is None:
        raise HTTPException(404, "edition not found")
    return _edition_out(ed, lang)


@router.get("/editions/{edition_id}/go")
async def go_to_registration(
    edition_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    race: UUID | None = None,
) -> RedirectResponse:
    """Tracked outbound redirect to the official registration (or info) page."""
    ed = await session.get(EventEdition, edition_id)
    if ed is None:
        raise HTTPException(404, "edition not found")
    target = ed.registration_url
    if race is not None:
        r = (
            await session.execute(
                select(Race)
                .where(Race.id == race, Race.edition_id == edition_id)
                .options(selectinload(Race.registration_windows))
            )
        ).scalar_one_or_none()
        if r is not None:
            window = max(r.registration_windows, key=lambda w: w.state_checked_at, default=None)
            if window and window.url:
                target = window.url
    target = target or ed.info_url
    if not target or urlparse(target).scheme not in ("http", "https"):
        raise HTTPException(404, "no registration link known for this edition")
    client = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")[:512]
    session.add(
        OutboundClick(
            edition_id=edition_id,
            race_id=race,
            target_url=target,
            anon_session_hash=pseudonymous_client_hash(client, ua),
        )
    )
    await session.commit()
    resp = RedirectResponse(target, status_code=302)
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _ics_escape(v: str) -> str:
    return (
        v.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    """RFC 5545 §3.1: lines longer than 75 octets are folded with CRLF + space."""
    out, cur = [], b""
    for ch in line:
        enc = ch.encode()
        if len(cur) + len(enc) > 75:
            out.append(cur.decode())
            cur = b" "
        cur += enc
    out.append(cur.decode())
    return "\r\n".join(out)


@router.get("/editions/{edition_id}/calendar.ics")
async def edition_calendar(
    edition_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    """All-day iCalendar entry for an edition ("Add to calendar")."""
    ed = (
        await session.execute(
            select(EventEdition)
            .where(EventEdition.id == edition_id)
            .options(selectinload(EventEdition.event), selectinload(EventEdition.venue))
        )
    ).scalar_one_or_none()
    if ed is None or ed.event.status != "published":
        raise HTTPException(404, "edition not found")
    end = (ed.end_date or ed.start_date) + timedelta(days=1)  # DTEND is exclusive
    venue = ed.venue
    location = ", ".join(x for x in [venue.name, venue.city, venue.country] if x) if venue else ""
    page = f"{get_settings().public_web_url.rstrip('/')}/events/{ed.event.slug}"
    link = ed.registration_url or ed.info_url or ed.event.website or page
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Sports Events Hub//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{ed.id}@sports-events-hub",
        f"DTSTAMP:{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
        f"DTSTART;VALUE=DATE:{ed.start_date:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        f"SUMMARY:{_ics_escape(f'{ed.event.name} {ed.year}')}",
        f"LOCATION:{_ics_escape(location)}",
        f"DESCRIPTION:{_ics_escape(f'Official info and registration: {link}')}",
        f"URL:{link}",
        "STATUS:" + ("CANCELLED" if ed.status == "cancelled" else "CONFIRMED"),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    body = "\r\n".join(_ics_fold(ln) for ln in lines) + "\r\n"
    filename = f"{ed.event.slug}-{ed.year}.ics"
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
        },
    )
