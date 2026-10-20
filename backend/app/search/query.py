"""Builds and runs the search against the `race_search` materialized view."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.search import SearchFilters, SearchHit, SearchResponse

FACET_COLUMNS = ["sport_slug", "discipline_slug", "country", "reg_state"]
DEMO_SOURCE_KEYS = ["sample"]

_HAVERSINE = (
    "2 * 6371 * asin(sqrt("
    "power(sin((radians(lat) - radians(:near_lat)) / 2), 2) + "
    "cos(radians(:near_lat)) * cos(radians(lat)) * "
    "power(sin((radians(lon) - radians(:near_lon)) / 2), 2)))"
)


def _build_where(f: SearchFilters, params: dict[str, Any]) -> list[str]:
    where: list[str] = ["edition_status <> 'cancelled'"]

    if f.sport:
        params["sport"] = f.sport
        where.append("sport_slug = ANY(:sport)")
    if f.discipline:
        params["discipline"] = f.discipline
        where.append("discipline_slug = ANY(:discipline)")
    if f.country:
        params["country"] = [c.upper() for c in f.country]
        where.append("country = ANY(:country)")
    if f.region:
        params["region"] = f"%{f.region}%"
        where.append("region ILIKE :region")
    if f.date_from:
        params["date_from"] = f.date_from
        where.append("start_date >= :date_from")
    else:
        params["date_from"] = date.today()
        where.append("start_date >= :date_from")
    if f.date_to:
        params["date_to"] = f.date_to
        where.append("start_date <= :date_to")
    if f.reg_state:
        params["reg_state"] = f.reg_state
        where.append("reg_state = ANY(:reg_state)")
    if f.price_max is not None:
        params["price_max"] = f.price_max
        where.append("price_from IS NOT NULL AND price_from <= :price_max")
    if f.source:
        params["source"] = f.source
        where.append("source_keys && CAST(:source AS text[])")
    if not f.include_demo:
        params["demo_sources"] = DEMO_SOURCE_KEYS
        where.append("NOT (source_keys && CAST(:demo_sources AS text[]))")
    if f.relay is not None:
        params["relay"] = f.relay
        where.append("relay = :relay")
    if f.near_lat is not None and f.near_lon is not None:
        params["near_lat"] = f.near_lat
        params["near_lon"] = f.near_lon
        params["radius_km"] = f.radius_km or 100.0
        where.append(f"lat IS NOT NULL AND {_HAVERSINE} <= :radius_km")
    for i, af in enumerate(f.attributes):
        key = f"attr_k{i}"
        val = f"attr_v{i}"
        params[key] = af.key
        if af.op == "eq":
            params[val] = str(af.value).lower() if isinstance(af.value, bool) else str(af.value)
            where.append(f"attributes ->> :{key} = :{val}")
        elif af.op == "in":
            params[val] = [str(v) for v in (af.value if isinstance(af.value, list) else [af.value])]
            where.append(f"attributes ->> :{key} = ANY(:{val})")
        elif af.op in ("lte", "gte"):
            params[val] = float(af.value)
            cmp = "<=" if af.op == "lte" else ">="
            where.append(
                f"jsonb_typeof(attributes -> :{key}) = 'number' "
                f"AND (attributes ->> :{key})::numeric {cmp} :{val}"
            )
    if f.q:
        params["q"] = f.q
        where.append(
            "(search_vector @@ websearch_to_tsquery('simple', immutable_unaccent(:q)) "
            "OR similarity(event_name, :q) > 0.25)"
        )
    return where


def _order(f: SearchFilters) -> str:
    if f.sort == "date":
        return "start_date ASC, event_name ASC"
    if f.sort == "price":
        return "price_from ASC NULLS LAST, start_date ASC"
    if f.sort == "distance" and f.near_lat is not None:
        return "distance_km ASC NULLS LAST, start_date ASC"
    if f.q:
        return "score DESC, start_date ASC"
    return "start_date ASC, event_name ASC"


async def run_search(session: AsyncSession, f: SearchFilters) -> SearchResponse:
    params: dict[str, Any] = {}
    where = _build_where(f, params)
    where_sql = " AND ".join(where)

    distance_expr = (
        f"{_HAVERSINE} AS distance_km"
        if f.near_lat is not None and f.near_lon is not None
        else "NULL::float AS distance_km"
    )
    if f.q:
        score_expr = (
            "0.6 * ts_rank_cd(search_vector, websearch_to_tsquery('simple', "
            "immutable_unaccent(:q))) + 0.3 * similarity(event_name, :q) + "
            "0.1 * COALESCE(data_quality_score, 0.5) AS score"
        )
    else:
        score_expr = "NULL::float AS score"

    sql = text(
        f"""
        SELECT race_id, edition_id, event_slug, event_name, race_name, sport_slug,
               discipline_slug, start_date, end_date, city, region, country, lat, lon,
               distances, attributes, relay, reg_state, reg_opens_at, reg_closes_at,
               reg_checked_at, price_from, currency, registration_url, info_url,
               source_keys, {distance_expr}, {score_expr}
        FROM race_search
        WHERE {where_sql}
        ORDER BY {_order(f)}
        LIMIT :limit OFFSET :offset
        """
    )
    params_page = {**params, "limit": f.limit, "offset": f.offset}
    rows = (await session.execute(sql, params_page)).mappings().all()

    total = (
        await session.execute(text(f"SELECT count(*) FROM race_search WHERE {where_sql}"), params)
    ).scalar_one()

    facets: dict[str, dict[str, int]] = {}
    for col in FACET_COLUMNS:
        fac_rows = (
            await session.execute(
                text(
                    f"SELECT {col} AS k, count(*) AS n FROM race_search WHERE {where_sql} "
                    f"GROUP BY {col} ORDER BY n DESC LIMIT 30"
                ),
                params,
            )
        ).all()
        facets[col] = {str(k): int(n) for k, n in fac_rows if k is not None}
    src_rows = (
        await session.execute(
            text(
                f"SELECT k, count(*) AS n FROM race_search, unnest(source_keys) AS k "
                f"WHERE {where_sql} GROUP BY k ORDER BY n DESC LIMIT 30"
            ),
            params,
        )
    ).all()
    facets["source"] = {str(k): int(n) for k, n in src_rows}

    hits = [SearchHit(**dict(r)) for r in rows]
    return SearchResponse(filters=f, total=int(total), results=hits, facets=facets)
