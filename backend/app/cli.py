"""Operational CLI: `python -m app.cli --help`"""

from __future__ import annotations

import asyncio
import json

import typer
from sqlalchemy import select

from app.core.db import dispose_engine, get_session_factory
from app.models import Discipline, Source, Sport
from app.taxonomy import DISCIPLINES, SPORTS

cli = typer.Typer(help="Sports Events Hub operations")


def run_async(coro):
    """asyncio.run + engine disposal, so repeated commands never share a dead event loop."""

    async def _wrap():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(_wrap())


async def _seed_taxonomy() -> None:
    async with get_session_factory()() as session:
        existing = {s.slug: s for s in (await session.execute(select(Sport))).scalars()}
        for s in SPORTS:
            if s["slug"] not in existing:
                sport = Sport(slug=s["slug"], name_i18n=s["name"])
                session.add(sport)
                existing[s["slug"]] = sport
        await session.flush()
        have = {(d.sport_id, d.slug) for d in (await session.execute(select(Discipline))).scalars()}
        for sport_slug, slug, de, en, dist in DISCIPLINES:
            sport = existing[sport_slug]
            if (sport.id, slug) not in have:
                session.add(
                    Discipline(
                        sport_id=sport.id,
                        slug=slug,
                        name_i18n={"de": de, "en": en},
                        canonical_distances=dist,
                    )
                )
        await session.commit()


async def _ensure_source(
    key: str,
    name: str,
    kind: str,
    connector: str,
    config: dict,
    trust: int,
    *,
    rate_limit_rps: float | None = None,
    keep_config: bool = False,
) -> bool:
    """Create or update a source. Returns True when it was created."""
    async with get_session_factory()() as session:
        src = (await session.execute(select(Source).where(Source.key == key))).scalar_one_or_none()
        created = src is None
        if src is None:
            src = Source(key=key, name=name, kind=kind, connector=connector, config=config)
            session.add(src)
        src.name, src.kind, src.connector, src.trust_score = name, kind, connector, trust
        if not (keep_config and not created):
            src.config = config
        if rate_limit_rps is not None:
            src.rate_limit_rps = rate_limit_rps
        await session.commit()
        return created


async def _sync_catalog(keep_config: bool = True) -> list[tuple[str, str]]:
    """Register every catalog source whose credentials are configured."""
    from app.core.config import get_settings
    from app.ingestion.catalog import CATALOG

    settings = get_settings()
    out: list[tuple[str, str]] = []
    for spec in CATALOG:
        missing = spec.missing(settings)
        if missing:
            out.append((spec.key, f"skipped — set {', '.join(missing)}"))
            continue
        created = await _ensure_source(
            spec.key,
            spec.name,
            spec.kind,
            spec.connector,
            dict(spec.config),
            spec.trust,
            rate_limit_rps=spec.rate_limit_rps,
            keep_config=keep_config,
        )
        out.append((spec.key, "registered" if created else "updated"))
    return out


async def _run(key: str) -> dict:
    from app.ingestion.pipeline import run_source

    async with get_session_factory()() as session:
        return await run_source(session, key)


@cli.command()
def seed(
    with_sample: bool = typer.Option(
        True, "--with-sample/--no-sample", help="also load ~100 fictional demo editions"
    ),
) -> None:
    """Seed the taxonomy, register the real API sources and (by default) load demo data."""
    from app.ingestion.catalog import SAMPLE

    run_async(_seed_taxonomy())
    typer.echo("taxonomy seeded")
    if with_sample:
        run_async(
            _ensure_source(
                SAMPLE.key,
                SAMPLE.name,
                SAMPLE.kind,
                SAMPLE.connector,
                dict(SAMPLE.config),
                SAMPLE.trust,
            )
        )
        report = run_async(_run(SAMPLE.key))
        typer.echo(json.dumps(report, default=str))
    for key, status in run_async(_sync_catalog()):
        typer.echo(f"source {key:16} {status}")
    typer.echo("next: python -m app.cli run-all   (fetch real events from the APIs above)")


@cli.command("sync-sources")
def sync_sources(
    reset_config: bool = typer.Option(
        False, help="overwrite existing source configs with the catalog defaults"
    ),
) -> None:
    """Register/update the built-in real API sources (docs/DATA_SOURCES.md)."""
    for key, status in run_async(_sync_catalog(keep_config=not reset_config)):
        typer.echo(f"source {key:16} {status}")


@cli.command("catalog")
def catalog_cmd() -> None:
    """Show the built-in data sources and whether their credentials are configured."""
    from app.core.config import get_settings
    from app.ingestion.catalog import CATALOG

    settings = get_settings()
    for spec in CATALOG:
        missing = spec.missing(settings)
        state = "ready" if not missing else f"needs {', '.join(missing)}"
        typer.echo(f"{spec.key:16} {spec.connector:16} {state:32} {spec.docs_url}")


@cli.command("reset-data")
def reset_data(yes: bool = typer.Option(False, "--yes", help="skip confirmation")) -> None:
    """Delete all events, editions, races, venues, organizers and source records.

    Keeps taxonomy and source definitions. Use before re-seeding demo data.
    """
    from sqlalchemy import text

    if not yes and not typer.confirm("Delete ALL event data?"):
        raise typer.Abort()

    async def _reset() -> None:
        async with get_session_factory()() as session:
            await session.execute(
                text(
                    "TRUNCATE source_record, price_tier, registration_window, race_attribute, "
                    "race, event_edition, event, venue, organizer, outbound_click CASCADE"
                )
            )
            await session.commit()
            await session.execute(text("REFRESH MATERIALIZED VIEW race_search"))
            await session.commit()

    run_async(_reset())
    typer.echo("event data deleted")


@cli.command("add-source")
def add_source(
    key: str,
    name: str,
    connector: str = typer.Option(
        ...,
        help="jsonld | ical | llm_page | world_triathlon | runsignup | ticketmaster | wikidata",
    ),
    kind: str = typer.Option("scrape", help="api | feed | scrape | submission | manual"),
    config: str = typer.Option(
        "{}", help='JSON, e.g. \'{"urls": ["https://..."], "sport_slug": "triathlon"}\''
    ),
    trust: int = typer.Option(50),
) -> None:
    """Register (or update) a source. Put credentials in the environment, never in config."""
    from app.core.redact import SENSITIVE_KEYS
    from app.ingestion.connectors import get_connector

    get_connector(connector)  # fail fast on typos
    cfg = json.loads(config)
    leaked = [k for k in cfg if SENSITIVE_KEYS.search(k)]
    if leaked:
        raise typer.BadParameter(f"do not store secrets in source config: {leaked}")
    run_async(_ensure_source(key, name, kind, connector, cfg, trust))
    typer.echo(f"source '{key}' saved")


@cli.command("run-source")
def run_source_cmd(key: str) -> None:
    """Run one ingestion source now."""
    typer.echo(json.dumps(run_async(_run(key)), default=str))


@cli.command("run-all")
def run_all() -> None:
    """Run every enabled source (what a scheduler would do)."""

    async def _all() -> None:
        async with get_session_factory()() as session:
            keys = [
                s.key
                for s in (
                    await session.execute(select(Source).where(Source.enabled.is_(True)))
                ).scalars()
            ]
        for k in keys:
            try:
                typer.echo(json.dumps(await _run(k), default=str))
            except Exception as e:  # noqa: BLE001
                typer.echo(f"{k}: FAILED {e}")

    run_async(_all())


@cli.command("list-sources")
def list_sources() -> None:
    async def _ls() -> None:
        async with get_session_factory()() as session:
            for s in (await session.execute(select(Source).order_by(Source.key))).scalars():
                typer.echo(
                    f"{s.key:20} {s.connector:15} enabled={s.enabled} "
                    f"last_success={s.last_success_at} "
                    f"error={s.last_error or '-'}"
                )

    run_async(_ls())


@cli.command("refresh-search")
def refresh_search_cmd() -> None:
    """Refresh the race_search materialized view."""
    from app.ingestion.publish import refresh_search

    async def _r() -> None:
        async with get_session_factory()() as session:
            await refresh_search(session)

    run_async(_r())
    typer.echo("race_search refreshed")


if __name__ == "__main__":
    cli()
