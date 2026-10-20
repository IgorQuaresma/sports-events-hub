"""Public data-source directory: who provides the data, under which terms, how fresh it is."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.ingestion.catalog import BY_KEY, ENRICHMENT_PROVIDERS
from app.models import Source, SourceRecord

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    key: str
    name: str
    kind: str
    homepage: str | None
    license: str | None
    attribution: str | None
    is_demo: bool
    editions: int
    last_success_at: datetime | None


class EnrichmentOut(BaseModel):
    key: str
    name: str
    purpose: str
    homepage: str
    license: str
    attribution: str


class SourcesOut(BaseModel):
    sources: list[SourceOut]
    enrichment: list[EnrichmentOut]


@router.get("/sources", response_model=SourcesOut)
async def list_public_sources(
    response: Response, session: Annotated[AsyncSession, Depends(get_session)]
) -> SourcesOut:
    """Enabled sources with attribution. Never exposes config, errors or credentials."""
    response.headers["Cache-Control"] = "public, max-age=300"
    counts = dict(
        (
            await session.execute(
                select(SourceRecord.source_id, func.count(func.distinct(SourceRecord.edition_id)))
                .where(SourceRecord.edition_id.is_not(None))
                .group_by(SourceRecord.source_id)
            )
        ).all()
    )
    rows = (
        await session.execute(select(Source).where(Source.enabled.is_(True)).order_by(Source.name))
    ).scalars()
    out: list[SourceOut] = []
    for s in rows:
        spec = BY_KEY.get(s.key)
        out.append(
            SourceOut(
                key=s.key,
                name=spec.name if spec else s.name,
                kind=s.kind,
                homepage=spec.homepage if spec else s.base_url,
                license=spec.license if spec else None,
                attribution=spec.attribution if spec else None,
                is_demo=s.key == "sample",
                editions=int(counts.get(s.id, 0)),
                last_success_at=s.last_success_at,
            )
        )
    return SourcesOut(sources=out, enrichment=[EnrichmentOut(**p) for p in ENRICHMENT_PROVIDERS])
