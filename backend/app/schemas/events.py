from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PriceTierOut(BaseModel):
    label: str | None
    amount: Decimal
    currency: str
    valid_from: datetime | None
    valid_until: datetime | None


class RegistrationWindowOut(BaseModel):
    state: str
    opens_at: datetime | None
    closes_at: datetime | None
    state_checked_at: datetime
    url: str | None
    price_tiers: list[PriceTierOut]


class RaceOut(BaseModel):
    id: UUID
    name: str
    discipline_slug: str
    start_time: datetime | None
    distances: dict[str, Any]
    attributes: dict[str, Any]
    participant_limit: int | None
    participants_registered: int | None
    relay: bool
    team: bool
    registration: RegistrationWindowOut | None


class VenueOut(BaseModel):
    name: str | None
    street: str | None
    postal_code: str | None
    city: str | None
    region: str | None
    country: str
    lat: float | None
    lon: float | None


class ProvenanceOut(BaseModel):
    source_key: str
    source_name: str
    source_kind: str
    url: str
    fetched_at: datetime
    parse_method: str | None
    parse_confidence: float | None


class EditionOut(BaseModel):
    id: UUID
    year: int
    start_date: date
    end_date: date | None
    status: str
    venue: VenueOut | None
    registration_url: str | None
    info_url: str | None
    registration_platform: str | None
    summary: str | None
    data_quality_score: float | None
    last_verified_at: datetime | None
    races: list[RaceOut]
    provenance: list[ProvenanceOut]


class EditionSummaryOut(BaseModel):
    id: UUID
    year: int
    start_date: date
    status: str
    city: str | None
    country: str | None


class EventOut(BaseModel):
    id: UUID
    slug: str
    name: str
    sport_slug: str
    website: str | None
    organizer_name: str | None
    description: str | None
    editions: list[EditionSummaryOut]
    next_edition: EditionOut | None
    is_demo: bool = False
