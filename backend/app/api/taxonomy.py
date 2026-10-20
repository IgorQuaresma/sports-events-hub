from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_session
from app.models import Sport
from app.taxonomy import ATTRIBUTE_KEYS, COUNTRIES

router = APIRouter(tags=["taxonomy"])


@router.get("/taxonomy")
async def taxonomy(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    sports = (
        (await session.execute(select(Sport).options(selectinload(Sport.disciplines))))
        .scalars()
        .all()
    )
    return {
        "sports": [
            {
                "slug": s.slug,
                "name": s.name_i18n,
                "disciplines": [
                    {"slug": d.slug, "name": d.name_i18n, "distances": d.canonical_distances}
                    for d in s.disciplines
                ],
            }
            for s in sorted(sports, key=lambda s: s.slug)
        ],
        "attributes": ATTRIBUTE_KEYS,
        "countries": COUNTRIES,
        "registration_states": ["not_open", "open", "waitlist", "sold_out", "closed", "unknown"],
    }
