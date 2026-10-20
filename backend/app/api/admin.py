"""Admin and ingest endpoints (service-token protected). Real admin roles come in phase 3."""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session, get_session_factory
from app.core.redact import redact_config
from app.core.security import require_service_token
from app.ingestion.pipeline import ingest_candidates, run_source
from app.models import Source
from app.schemas.candidate import EventCandidate

router = APIRouter(tags=["admin"], dependencies=[Depends(require_service_token)])


@router.get("/admin/sources")
async def list_sources(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Source).order_by(Source.key))).scalars().all()
    return [
        {
            "key": s.key,
            "name": s.name,
            "kind": s.kind,
            "connector": s.connector,
            "enabled": s.enabled,
            "trust_score": s.trust_score,
            "last_run_at": s.last_run_at,
            "last_success_at": s.last_success_at,
            "last_error": s.last_error,
            "rate_limit_rps": s.rate_limit_rps,
            "config": redact_config(s.config),
        }
        for s in rows
    ]


async def _run_in_background(source_key: str) -> None:
    async with get_session_factory()() as session:
        await run_source(session, source_key)


@router.post("/admin/sources/{key}/run")
async def trigger_source(
    key: str, background: BackgroundTasks, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, str]:
    src = (await session.execute(select(Source).where(Source.key == key))).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "unknown source")
    background.add_task(_run_in_background, key)
    return {"status": "scheduled", "source": key}


@router.post("/ingest/candidates")
async def ingest(
    candidates: Annotated[list[EventCandidate], Body(max_length=500)],
    session: Annotated[AsyncSession, Depends(get_session)],
    source_key: str = Query(default="manual", pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$"),
) -> dict[str, Any]:
    """Push feed for partners / FME workspaces: a list of `EventCandidate` objects."""
    report = await ingest_candidates(session, source_key, candidates, parse_method="api")
    return report
