from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import limit_parse_requests
from app.schemas.search import AttributeFilter, ParsedQuery, SearchFilters, SearchResponse
from app.search.nlq import parse_query
from app.search.query import run_search

router = APIRouter(tags=["search"])

MAX_LIST_ITEMS = 20


def _csv(v: str | None) -> list[str]:
    items = [x.strip() for x in v.split(",") if x.strip()] if v else []
    return items[:MAX_LIST_ITEMS]


def _bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=422, detail=msg)


def _attr_filters(attr: list[str]) -> list[AttributeFilter]:
    """attr=wetsuit_rule:allowed,mandatory · attr=elevation_gain_m<=300 · attr=draft_legal:true"""
    out: list[AttributeFilter] = []
    for raw in attr:
        try:
            if "<=" in raw:
                k, v = raw.split("<=", 1)
                out.append(AttributeFilter(key=k.strip(), op="lte", value=float(v)))
            elif ">=" in raw:
                k, v = raw.split(">=", 1)
                out.append(AttributeFilter(key=k.strip(), op="gte", value=float(v)))
            elif ":" in raw:
                k, v = raw.split(":", 1)
                vals = _csv(v)
                if len(vals) == 1:
                    out.append(AttributeFilter(key=k.strip(), op="eq", value=vals[0]))
                else:
                    out.append(AttributeFilter(key=k.strip(), op="in", value=vals))
            else:
                raise ValueError
        except ValueError:
            raise _bad_request(
                f"invalid attr filter {raw!r}; use key:value, key<=number or key>=number"
            ) from None
    return out


def _near(near: str | None) -> tuple[float | None, float | None]:
    if not near:
        return None, None
    try:
        lat_s, lon_s = near.split(",")
        return float(lat_s), float(lon_s)
    except ValueError:
        raise _bad_request("near must be 'lat,lon'") from None


@router.get("/search", response_model=SearchResponse)
async def search(
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    sport: str | None = None,
    discipline: str | None = None,
    country: str | None = None,
    region: Annotated[str | None, Query(max_length=100)] = None,
    near: str | None = Query(default=None, description="lat,lon"),
    radius_km: Annotated[float | None, Query(gt=0, le=1000)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    reg_state: str | None = None,
    price_max: Annotated[float | None, Query(ge=0)] = None,
    relay: bool | None = None,
    attr: Annotated[list[str] | None, Query(max_length=10)] = None,
    source: str | None = None,
    include_demo: bool = True,
    sort: Literal["relevance", "date", "distance", "price"] = "relevance",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> SearchResponse:
    near_lat, near_lon = _near(near)
    try:
        f = SearchFilters(
            q=q or None,
            sport=_csv(sport),
            discipline=_csv(discipline),
            country=_csv(country),
            region=region,
            near_lat=near_lat,
            near_lon=near_lon,
            radius_km=radius_km,
            date_from=date_from,
            date_to=date_to,
            reg_state=_csv(reg_state),
            price_max=price_max,
            relay=relay,
            attributes=_attr_filters(attr or []),
            source=_csv(source),
            include_demo=include_demo,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ValidationError as e:
        raise _bad_request(e.errors(include_url=False, include_context=False)[0]["msg"]) from None
    return await run_search(session, f)


class ParseRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)


@router.post(
    "/search/parse", response_model=ParsedQuery, dependencies=[Depends(limit_parse_requests)]
)
async def parse(body: ParseRequest) -> ParsedQuery:
    filters, chips, method = await parse_query(body.query)
    return ParsedQuery(filters=filters, chips=chips, method=method)


@router.post("/search/structured", response_model=SearchResponse)
async def search_structured(
    f: SearchFilters, session: Annotated[AsyncSession, Depends(get_session)]
) -> SearchResponse:
    """Search with a full `SearchFilters` body (what the NL parser returns)."""
    return await run_search(session, f)
