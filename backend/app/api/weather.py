"""Race-day weather forecast via Open-Meteo (keyless, CC BY 4.0).

Only for editions with coordinates and a start date within the 16-day forecast horizon.
The upstream host is fixed by configuration; responses are cached in-process for an hour.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import get_session
from app.models import EventEdition

log = logging.getLogger("weather")
router = APIRouter(tags=["events"])

FORECAST_DAYS = 16
CACHE_TTL_S = 3600
_cache: dict[tuple[float, float, date], tuple[float, WeatherOut]] = {}

# WMO weather interpretation codes (subset) → short English label
WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


class WeatherOut(BaseModel):
    available: bool
    reason: str | None = None
    date: dt.date | None = None  # module alias: the field name shadows the type
    summary: str | None = None
    weather_code: int | None = None
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    precipitation_probability_pct: int | None = None
    wind_max_kmh: float | None = None
    attribution: str = "Weather data by Open-Meteo.com (CC BY 4.0)"
    attribution_url: str = "https://open-meteo.com/"


def _unavailable(reason: str) -> WeatherOut:
    return WeatherOut(available=False, reason=reason)


async def _forecast(lat: float, lon: float, day: date) -> WeatherOut:
    key = (round(lat, 2), round(lon, 2), day)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,wind_speed_10m_max",
        "timezone": "auto",
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
    }
    s = get_settings()
    async with httpx.AsyncClient(
        timeout=8.0, headers={"User-Agent": s.fetcher_user_agent}
    ) as client:
        resp = await client.get(s.open_meteo_url, params=params)
    resp.raise_for_status()
    daily = resp.json().get("daily") or {}

    def first(name: str):
        values = daily.get(name) or [None]
        return values[0]

    code = first("weather_code")
    out = WeatherOut(
        available=True,
        date=day,
        weather_code=code,
        summary=WMO.get(code) if code is not None else None,
        temp_max_c=first("temperature_2m_max"),
        temp_min_c=first("temperature_2m_min"),
        precipitation_probability_pct=first("precipitation_probability_max"),
        wind_max_kmh=first("wind_speed_10m_max"),
    )
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.monotonic(), out)
    return out


@router.get("/editions/{edition_id}/weather", response_model=WeatherOut)
async def edition_weather(
    edition_id: UUID,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WeatherOut:
    """Forecast for the edition's start day, when it is within the forecast horizon."""
    response.headers["Cache-Control"] = "public, max-age=1800"
    if not get_settings().weather_enabled:
        return _unavailable("disabled")
    ed = (
        await session.execute(
            select(EventEdition)
            .where(EventEdition.id == edition_id)
            .options(selectinload(EventEdition.venue))
        )
    ).scalar_one_or_none()
    if ed is None:
        raise HTTPException(404, "edition not found")
    today = date.today()
    if ed.start_date < today:
        return _unavailable("past")
    if ed.start_date > today + timedelta(days=FORECAST_DAYS - 1):
        return _unavailable("too_far_ahead")
    if ed.venue is None or ed.venue.lat is None or ed.venue.lon is None:
        return _unavailable("no_location")
    try:
        return await _forecast(ed.venue.lat, ed.venue.lon, ed.start_date)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("open-meteo failed: %s", e)
        return _unavailable("upstream_error")
