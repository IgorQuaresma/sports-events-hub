"""Canonical ingestion contract shared by connectors, AI extraction and the ingest API.

Every data source — an API, a JSON-LD block, an iCal feed, an LLM reading a page — produces
`EventCandidate` objects. The pipeline normalizes, resolves and publishes them.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class LocationCandidate(BaseModel):
    text: str | None = None  # free-form, e.g. "Stadtpark, Hamburg"
    name: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    lat: float | None = None
    lon: float | None = None

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PriceCandidate(BaseModel):
    label: str | None = None
    amount: float
    currency: str = "EUR"
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class RegistrationCandidate(BaseModel):
    url: HttpUrl | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    state: str = Field(
        default="unknown",
        pattern="^(not_open|open|waitlist|sold_out|closed|unknown)$",
    )
    prices: list[PriceCandidate] = Field(default_factory=list)
    platform: str | None = None


class RaceCandidate(BaseModel):
    name: str
    discipline_slug: str | None = Field(
        default=None, description="taxonomy slug; inferred by the normalizer when missing"
    )
    start_time: datetime | None = None
    distances: dict[str, float] = Field(
        default_factory=dict,
        description="swim_m, bike_km, run_km, total_km, elevation_gain_m ...",
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="wetsuit_rule, surface, draft_legal, water_type, cutoff_minutes, ...",
    )
    participant_limit: int | None = None
    participants_registered: int | None = None
    relay: bool = False
    team: bool = False
    registration: RegistrationCandidate | None = None


class EventCandidate(BaseModel):
    name: str
    sport_slug: str
    start_date: date
    end_date: date | None = None
    location: LocationCandidate = Field(default_factory=LocationCandidate)
    organizer_name: str | None = None
    website: HttpUrl | None = None
    registration_url: HttpUrl | None = None
    registration_platform: str | None = None
    races: list[RaceCandidate] = Field(default_factory=list)
    description: str | None = None
    language: str = "de"
    source_url: HttpUrl
    external_id: str | None = None
    status: str = Field(default="scheduled", pattern="^(scheduled|cancelled|postponed|finished)$")
    evidence: dict[str, str] = Field(
        default_factory=dict, description="field -> quoted snippet from the source (AI extraction)"
    )
