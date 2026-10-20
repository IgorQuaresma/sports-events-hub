import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin


class Sport(UUIDMixin, Base):
    __tablename__ = "sport"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_i18n: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    disciplines: Mapped[list["Discipline"]] = relationship(back_populates="sport")


class Discipline(UUIDMixin, Base):
    __tablename__ = "discipline"
    __table_args__ = (UniqueConstraint("sport_id", "slug"),)

    sport_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sport.id"))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name_i18n: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    canonical_distances: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    sport: Mapped[Sport] = relationship(back_populates="disciplines")
