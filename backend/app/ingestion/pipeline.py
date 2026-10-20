"""Pipeline orchestration: discover → fetch → store raw → parse → normalize → resolve/publish."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redact import redact_text, redact_url
from app.ingestion.base import ParseResult, RawDocument
from app.ingestion.connectors import get_connector
from app.ingestion.fetcher import FetchError, HttpFetcher
from app.ingestion.geocode import NominatimGeocoder, enrich_coordinates
from app.ingestion.normalize import normalize
from app.ingestion.publish import refresh_search, upsert_candidate
from app.models import Source, SourceRecord
from app.schemas.candidate import EventCandidate

log = logging.getLogger("ingest")


def _store_raw(source_key: str, raw: RawDocument, digest: str) -> str:
    s = get_settings()
    now = raw.fetched_at
    rel = f"{source_key}/{now:%Y/%m}/{digest}.bin"
    path = s.raw_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw.body)
    return rel


async def _publish_results(
    session: AsyncSession,
    source: Source,
    raw: RawDocument,
    digest: str,
    raw_key: str,
    results: list[ParseResult],
    defaults: dict[str, Any],
    report: dict[str, Any],
    geocoder: NominatimGeocoder | None = None,
) -> None:
    for res in results:
        try:
            cand = normalize(res.candidate, defaults)
            cand = await enrich_coordinates(session, cand, geocoder)
            edition, created = await upsert_candidate(session, cand)
        except Exception as e:  # noqa: BLE001 — one bad candidate must not stop the run
            log.exception("candidate failed: %s", res.candidate.name)
            report["errors"].append(f"{res.candidate.name}: {e}")
            await session.rollback()
            continue
        rec_url = redact_url(str(res.candidate.source_url) or raw.url)
        rec = (
            await session.execute(
                select(SourceRecord).where(
                    SourceRecord.source_id == source.id,
                    SourceRecord.url == rec_url,
                    SourceRecord.content_hash == digest,
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            rec = SourceRecord(source_id=source.id, url=rec_url, content_hash=digest)
            session.add(rec)
        rec.external_id = raw.external_id or res.candidate.external_id
        rec.fetched_at = raw.fetched_at
        rec.http_status = raw.http_status
        rec.raw_object_key = raw_key
        rec.parsed = cand.model_dump(mode="json")
        rec.parse_method = res.method
        rec.parse_confidence = res.confidence
        rec.edition_id = edition.id
        await session.commit()
        report["created" if created else "updated"] += 1


async def run_source(session: AsyncSession, source_key: str) -> dict[str, Any]:
    source = (await session.execute(select(Source).where(Source.key == source_key))).scalar_one()
    report: dict[str, Any] = {
        "source": source_key,
        "fetched": 0,
        "skipped_unchanged": 0,
        "created": 0,
        "updated": 0,
        "errors": [],
    }
    source.last_run_at = datetime.now(UTC)
    await session.commit()

    settings = get_settings()
    config = source.config or {}
    connector = get_connector(source.connector)(config)
    defaults = {"country": config.get("country")}
    min_delay = 1.0 / source.rate_limit_rps if source.rate_limit_rps else None
    fetcher = HttpFetcher(respect_robots=config.get("respect_robots", True), min_delay_s=min_delay)
    geocoder = NominatimGeocoder() if settings.geocoding_enabled else None
    # every configured secret, so no exception text can leak one into last_error / logs
    known_secrets = [
        settings.secret(n)
        for n in (
            "world_triathlon_api_key",
            "ticketmaster_api_key",
            "runsignup_api_key",
            "runsignup_api_secret",
            "anthropic_api_key",
        )
    ]
    try:
        async for item in connector.discover(fetcher):
            try:
                raw = await connector.fetch(item, fetcher)
            except FetchError as e:
                where = redact_url(item.url)
                report["errors"].append(str(e) if where in str(e) else f"{where}: {e}")
                continue
            report["fetched"] += 1
            digest = hashlib.sha256(raw.body).hexdigest()
            raw_key = _store_raw(source_key, raw, digest)
            seen = (
                await session.execute(
                    select(SourceRecord.id).where(
                        SourceRecord.source_id == source.id,
                        SourceRecord.content_hash == digest,
                    )
                )
            ).first()
            if seen and not (source.config or {}).get("force_reparse"):
                report["skipped_unchanged"] += 1
                continue
            try:
                results = await connector.parse(raw)
            except Exception as e:  # noqa: BLE001
                log.exception("parse failed for %s", raw.url)
                report["errors"].append(f"{raw.url}: parse failed: {e}")
                continue
            await _publish_results(
                session, source, raw, digest, raw_key, results, defaults, report, geocoder
            )
        report["errors"] = [redact_text(e, known_secrets) for e in report["errors"]]
        source.last_success_at = datetime.now(UTC)
        source.last_error = "; ".join(report["errors"])[:2000] or None
        await session.commit()
    except Exception as e:  # noqa: BLE001
        await session.rollback()
        source.last_error = redact_text(f"{type(e).__name__}: {e}", known_secrets)[:2000]
        await session.commit()
        raise
    finally:
        await fetcher.aclose()
        if geocoder is not None:
            await geocoder.aclose()
    await refresh_search(session)
    log.info("source %s done: %s", source_key, report)
    return report


async def ingest_candidates(
    session: AsyncSession, source_key: str, candidates: list[EventCandidate], parse_method: str
) -> dict[str, Any]:
    source = (
        await session.execute(select(Source).where(Source.key == source_key))
    ).scalar_one_or_none()
    if source is None:
        source = Source(
            key=source_key, kind="submission", name=source_key, connector="none", trust_score=70
        )
        session.add(source)
        await session.commit()
    report: dict[str, Any] = {
        "source": source_key,
        "fetched": len(candidates),
        "skipped_unchanged": 0,
        "created": 0,
        "updated": 0,
        "errors": [],
    }
    now = datetime.now(UTC)
    for c in candidates:
        body = c.model_dump_json().encode()
        digest = hashlib.sha256(body).hexdigest()
        raw = RawDocument(
            url=str(c.source_url), body=body, fetched_at=now, external_id=c.external_id
        )
        raw_key = _store_raw(source_key, raw, digest)
        await _publish_results(
            session,
            source,
            raw,
            digest,
            raw_key,
            [ParseResult(candidate=c, method=parse_method)],
            {},
            report,
        )
    await refresh_search(session)
    return report
