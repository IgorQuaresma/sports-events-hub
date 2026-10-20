from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AttributeFilter(BaseModel):
    key: str
    op: Literal["eq", "in", "lte", "gte"] = "eq"
    value: Any


class SearchFilters(BaseModel):
    """Structured search request. Produced by the UI or by the natural-language parser."""

    q: str | None = Field(default=None, max_length=200)
    sport: list[str] = Field(default_factory=list)
    discipline: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    region: str | None = None
    near_lat: float | None = Field(default=None, ge=-90, le=90)
    near_lon: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=1000)
    date_from: date | None = None
    date_to: date | None = None
    reg_state: list[str] = Field(default_factory=list)
    price_max: float | None = Field(default=None, ge=0)
    relay: bool | None = None
    attributes: list[AttributeFilter] = Field(default_factory=list, max_length=10)
    source: list[str] = Field(
        default_factory=list, description="only races reported by these sources"
    )
    include_demo: bool = Field(default=True, description="false hides demo/sample data")
    sort: Literal["relevance", "date", "distance", "price"] = "relevance"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchHit(BaseModel):
    race_id: UUID
    edition_id: UUID
    event_slug: str
    event_name: str
    race_name: str
    sport_slug: str
    discipline_slug: str
    start_date: date
    end_date: date | None
    city: str | None
    region: str | None
    country: str | None
    lat: float | None
    lon: float | None
    distance_km: float | None = None
    distances: dict[str, Any]
    attributes: dict[str, Any]
    relay: bool
    reg_state: str
    reg_opens_at: datetime | None
    reg_closes_at: datetime | None
    reg_checked_at: datetime | None
    price_from: Decimal | None
    currency: str | None
    registration_url: str | None
    info_url: str | None
    source_keys: list[str] = Field(default_factory=list)
    score: float | None = None


class SearchResponse(BaseModel):
    filters: SearchFilters
    total: int
    results: list[SearchHit]
    facets: dict[str, dict[str, int]]


class ParsedQuery(BaseModel):
    filters: SearchFilters
    chips: list[str]
    method: Literal["rules", "llm"]
