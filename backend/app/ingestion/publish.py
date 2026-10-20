"""Publisher: upsert a normalized candidate into the core tables."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from slugify import slugify
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ingestion.normalize import data_quality_score
from app.ingestion.resolve import find_existing_edition
from app.models import (
    Discipline,
    Event,
    EventEdition,
    Organizer,
    PriceTier,
    Race,
    RaceAttribute,
    RegistrationWindow,
    Sport,
    Venue,
)
from app.schemas.candidate import EventCandidate, RaceCandidate
from app.search.sql import REFRESH_RACE_SEARCH_SQL


async def _get_sport(session: AsyncSession, slug: str) -> Sport:
    sport = (await session.execute(select(Sport).where(Sport.slug == slug))).scalar_one_or_none()
    if sport is None:
        raise ValueError(f"unknown sport '{slug}' — seed the taxonomy or fix the connector")
    return sport


async def _get_discipline(session: AsyncSession, sport: Sport, slug: str) -> Discipline:
    d = (
        await session.execute(
            select(Discipline).where(Discipline.sport_id == sport.id, Discipline.slug == slug)
        )
    ).scalar_one_or_none()
    if d is None:
        d = (
            await session.execute(
                select(Discipline).where(
                    Discipline.sport_id == sport.id, Discipline.slug == "other"
                )
            )
        ).scalar_one_or_none()
    if d is None:
        raise ValueError(f"no discipline '{slug}' for sport {sport.slug}")
    return d


async def _find_existing_event(
    session: AsyncSession, sport: Sport, c: EventCandidate
) -> Event | None:
    """A new edition of an event we already know (same sport, same canonical slug)."""
    base = slugify(c.name)[:140]
    candidates = {base, slugify(f"{c.name} {c.location.city or ''}")[:150]}
    stmt = select(Event).where(Event.sport_id == sport.id, Event.slug.in_(candidates))
    return (await session.execute(stmt)).scalars().first()


async def _unique_slug(session: AsyncSession, base: str, city: str | None) -> str:
    slug = slugify(base)[:140] or "event"
    taken = (await session.execute(select(Event.id).where(Event.slug == slug))).first()
    if taken and city:
        slug = slugify(f"{base} {city}")[:150]
        taken = (await session.execute(select(Event.id).where(Event.slug == slug))).first()
    n = 2
    base_slug = slug
    while taken:
        slug = f"{base_slug}-{n}"
        taken = (await session.execute(select(Event.id).where(Event.slug == slug))).first()
        n += 1
    return slug


async def _get_or_create_organizer(
    session: AsyncSession, name: str | None, website
) -> Organizer | None:
    if not name:
        return None
    org = (
        await session.execute(select(Organizer).where(Organizer.name == name))
    ).scalar_one_or_none()
    if org is None:
        org = Organizer(name=name, website=str(website) if website else None)
        session.add(org)
        await session.flush()
    return org


def _apply_venue(venue: Venue, c: EventCandidate) -> None:
    loc = c.location
    venue.name = loc.name or venue.name
    venue.street = loc.street or venue.street
    venue.postal_code = loc.postal_code or venue.postal_code
    venue.city = loc.city or venue.city
    venue.region = loc.region or venue.region
    venue.country = loc.country or venue.country or "DE"
    if loc.lat is not None and loc.lon is not None:
        venue.lat, venue.lon = loc.lat, loc.lon
        venue.geocode_source = "source"


def _same_race(r: Race, rc: RaceCandidate, disc_slug: str) -> bool:
    return r.discipline.slug == disc_slug and r.name.strip().lower() == rc.name.strip().lower()


async def _apply_race(session: AsyncSession, race: Race, rc: RaceCandidate, now: datetime) -> None:
    race.name = rc.name
    race.start_time = rc.start_time or race.start_time
    if rc.distances:
        race.distances = rc.distances
    race.participant_limit = rc.participant_limit or race.participant_limit
    if rc.participants_registered is not None:
        race.participants_registered = rc.participants_registered
    race.relay, race.team = rc.relay, rc.team

    existing_attrs = {a.key: a for a in race.attributes}
    for k, v in rc.attributes.items():
        if k in existing_attrs:
            existing_attrs[k].value = v
        else:
            race.attributes.append(RaceAttribute(key=k, value=v))

    if rc.registration:
        reg = rc.registration
        latest = max(race.registration_windows, key=lambda w: w.state_checked_at, default=None)
        new_prices = [(p.label, Decimal(str(p.amount)), p.currency) for p in reg.prices]
        unchanged = (
            latest is not None
            and latest.state == reg.state
            and latest.opens_at == reg.opens_at
            and latest.closes_at == reg.closes_at
            and [(t.label, t.amount, t.currency) for t in latest.price_tiers] == new_prices
        )
        if unchanged:
            latest.state_checked_at = now
            if reg.url:
                latest.url = str(reg.url)
        else:
            window = RegistrationWindow(
                opens_at=reg.opens_at,
                closes_at=reg.closes_at,
                state=reg.state,
                state_checked_at=now,
                url=str(reg.url) if reg.url else None,
            )
            for p in reg.prices:
                window.price_tiers.append(
                    PriceTier(
                        label=p.label,
                        amount=Decimal(str(p.amount)),
                        currency=p.currency,
                        valid_from=p.valid_from,
                        valid_until=p.valid_until,
                    )
                )
            race.registration_windows.append(window)


async def upsert_candidate(session: AsyncSession, c: EventCandidate) -> tuple[EventEdition, bool]:
    """Create or update the edition described by `c`. Returns (edition, created)."""
    now = datetime.now(UTC)
    sport = await _get_sport(session, c.sport_slug)
    existing = await find_existing_edition(session, c)
    created = existing is None

    if existing is None:
        event = await _find_existing_event(session, sport, c)
        if event is None:
            organizer = await _get_or_create_organizer(session, c.organizer_name, c.website)
            slug = await _unique_slug(session, c.name, c.location.city)
            event = Event(
                slug=slug,
                name=c.name,
                sport_id=sport.id,
                organizer_id=organizer.id if organizer else None,
                website=str(c.website) if c.website else None,
                description_i18n={c.language: c.description} if c.description else None,
            )
            session.add(event)
            await session.flush()
        venue = Venue(country=c.location.country or "DE")
        _apply_venue(venue, c)
        session.add(venue)
        await session.flush()
        edition = EventEdition(
            event_id=event.id,
            year=c.start_date.year,
            start_date=c.start_date,
            end_date=c.end_date,
            venue_id=venue.id,
        )
        session.add(edition)
        await session.flush()
        edition = (
            await session.execute(
                select(EventEdition)
                .where(EventEdition.id == edition.id)
                .options(
                    selectinload(EventEdition.event),
                    selectinload(EventEdition.venue),
                    selectinload(EventEdition.races).selectinload(Race.discipline),
                    selectinload(EventEdition.races).selectinload(Race.attributes),
                    selectinload(EventEdition.races)
                    .selectinload(Race.registration_windows)
                    .selectinload(RegistrationWindow.price_tiers),
                )
            )
        ).scalar_one()
    else:
        edition = (
            await session.execute(
                select(EventEdition)
                .where(EventEdition.id == existing.id)
                .options(
                    selectinload(EventEdition.event),
                    selectinload(EventEdition.venue),
                    selectinload(EventEdition.races).selectinload(Race.discipline),
                    selectinload(EventEdition.races).selectinload(Race.attributes),
                    selectinload(EventEdition.races)
                    .selectinload(Race.registration_windows)
                    .selectinload(RegistrationWindow.price_tiers),
                )
            )
        ).scalar_one()
        event = edition.event
        event.website = str(c.website) if c.website else event.website
        if c.description:
            event.description_i18n = {**(event.description_i18n or {}), c.language: c.description}
        if edition.venue is None:
            edition.venue = Venue(country=c.location.country or "DE")
        _apply_venue(edition.venue, c)
        edition.end_date = c.end_date or edition.end_date

    edition.registration_url = (
        str(c.registration_url) if c.registration_url else edition.registration_url
    )
    edition.info_url = str(c.source_url) if not edition.info_url else edition.info_url
    edition.registration_platform = c.registration_platform or edition.registration_platform
    if c.status != "scheduled" or edition.status == "scheduled":
        edition.status = c.status
    edition.last_verified_at = now
    edition.data_quality_score = data_quality_score(c)

    for rc in c.races:
        disc = await _get_discipline(session, sport, rc.discipline_slug or "other")
        race = next((r for r in edition.races if _same_race(r, rc, disc.slug)), None)
        if race is None and len(c.races) == 1 and len(edition.races) == 1:
            race = edition.races[0]  # single-race events: same race, maybe renamed
            race.discipline = disc
        if race is None:
            race = Race(discipline_id=disc.id, name=rc.name)
            race.discipline = disc
            edition.races.append(race)
        await _apply_race(session, race, rc, now)

    await session.flush()
    return edition, created


async def refresh_search(session: AsyncSession) -> None:
    await session.execute(text(REFRESH_RACE_SEARCH_SQL))
    await session.commit()
