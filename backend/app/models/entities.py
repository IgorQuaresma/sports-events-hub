import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.taxonomy import Discipline, Sport


class Organizer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizer"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Source(UUIDMixin, TimestampMixin, Base):
    """A data origin (API, feed, scrape target, submissions) and the connector that reads it."""

    __tablename__ = "source"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # api|feed|scrape|submission|manual
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    connector: Mapped[str] = mapped_column(Text, nullable=False)  # registry key, e.g. "jsonld"
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    schedule_cron: Mapped[str | None] = mapped_column(Text)
    rate_limit_rps: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    trust_score: Mapped[int] = mapped_column(SmallInteger, default=50, server_default="50")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Event(UUIDMixin, TimestampMixin, Base):
    """The recurring event identity ("Hamburg Triathlon")."""

    __tablename__ = "event"

    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sport_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sport.id"))
    organizer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizer.id")
    )
    website: Mapped[str | None] = mapped_column(Text)
    description_i18n: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="published", server_default="published")

    sport: Mapped[Sport] = relationship()
    organizer: Mapped[Organizer | None] = relationship()
    editions: Mapped[list["EventEdition"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventEdition.start_date"
    )


class Venue(UUIDMixin, Base):
    __tablename__ = "venue"

    name: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    lat: Mapped[float | None] = mapped_column(
        Float
    )  # PostGIS geography planned; plain lat/lon for MVP
    lon: Mapped[float | None] = mapped_column(Float)
    geocode_source: Mapped[str | None] = mapped_column(Text)


class EventEdition(UUIDMixin, TimestampMixin, Base):
    """One dated occurrence of an event ("Hamburg Triathlon 2027")."""

    __tablename__ = "event_edition"
    __table_args__ = (UniqueConstraint("event_id", "year", "start_date"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("venue.id"))
    registration_url: Mapped[str | None] = mapped_column(Text)
    info_url: Mapped[str | None] = mapped_column(Text)
    registration_platform: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", server_default="scheduled")
    summary_i18n: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    data_quality_score: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="editions")
    venue: Mapped[Venue | None] = relationship()
    races: Mapped[list["Race"]] = relationship(
        back_populates="edition", cascade="all, delete-orphan", order_by="Race.name"
    )
    source_records: Mapped[list["SourceRecord"]] = relationship(back_populates="edition")


class Race(UUIDMixin, Base):
    """One startable category inside an edition ("Olympic distance, individual")."""

    __tablename__ = "race"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_edition.id", ondelete="CASCADE"), nullable=False
    )
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discipline.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distances: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    participant_limit: Mapped[int | None] = mapped_column(Integer)
    participants_registered: Mapped[int | None] = mapped_column(Integer)
    relay: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    team: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    edition: Mapped[EventEdition] = relationship(back_populates="races")
    discipline: Mapped[Discipline] = relationship()
    attributes: Mapped[list["RaceAttribute"]] = relationship(
        back_populates="race", cascade="all, delete-orphan"
    )
    registration_windows: Mapped[list["RegistrationWindow"]] = relationship(
        back_populates="race", cascade="all, delete-orphan"
    )


class RaceAttribute(Base):
    """Flexible race conditions: wetsuit_rule, elevation_gain_m, surface, draft_legal, ..."""

    __tablename__ = "race_attribute"

    race_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("race.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)

    race: Mapped[Race] = relationship(back_populates="attributes")


class RegistrationWindow(UUIDMixin, Base):
    __tablename__ = "registration_window"

    race_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("race.id", ondelete="CASCADE"), nullable=False
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # not_open | open | waitlist | sold_out | closed | unknown
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    state_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    url: Mapped[str | None] = mapped_column(Text)

    race: Mapped[Race] = relationship(back_populates="registration_windows")
    price_tiers: Mapped[list["PriceTier"]] = relationship(
        back_populates="window", cascade="all, delete-orphan", order_by="PriceTier.valid_until"
    )


class PriceTier(UUIDMixin, Base):
    __tablename__ = "price_tier"

    registration_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registration_window.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    window: Mapped[RegistrationWindow] = relationship(back_populates="price_tiers")


class SourceRecord(UUIDMixin, Base):
    """Immutable evidence: one fetched document and what we parsed out of it."""

    __tablename__ = "source_record"
    __table_args__ = (UniqueConstraint("source_id", "url", "content_hash"),)

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("source.id"))
    external_id: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parse_method: Mapped[str | None] = mapped_column(String(16))  # api|jsonld|ical|css|llm|fixture
    parse_confidence: Mapped[float | None] = mapped_column(Float)
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_edition.id", ondelete="SET NULL")
    )

    source: Mapped[Source] = relationship()
    edition: Mapped[EventEdition | None] = relationship(back_populates="source_records")


class OutboundClick(Base):
    __tablename__ = "outbound_click"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    race_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anon_session_hash: Mapped[str | None] = mapped_column(String(64))


class GeocodeCache(Base):
    """Cached geocoder answers (also negative ones) so each place is looked up once."""

    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
