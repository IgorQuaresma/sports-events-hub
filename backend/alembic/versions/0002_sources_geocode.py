"""race_search.source_keys + geocode cache

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen copy of the view introduced by this revision.
RACE_SEARCH_VIEW_V2 = """
CREATE MATERIALIZED VIEW race_search AS
WITH current_window AS (
    SELECT DISTINCT ON (rw.race_id)
        rw.race_id, rw.id AS window_id, rw.state, rw.opens_at, rw.closes_at,
        rw.state_checked_at, rw.url
    FROM registration_window rw
    ORDER BY rw.race_id, rw.state_checked_at DESC
),
price_from AS (
    SELECT pt.registration_window_id, MIN(pt.amount) AS amount, MIN(pt.currency) AS currency
    FROM price_tier pt
    WHERE pt.valid_until IS NULL OR pt.valid_until >= now()
    GROUP BY pt.registration_window_id
),
attrs AS (
    SELECT ra.race_id, jsonb_object_agg(ra.key, ra.value) AS attributes
    FROM race_attribute ra GROUP BY ra.race_id
),
edition_sources AS (
    SELECT sr.edition_id, array_agg(DISTINCT s.key::text ORDER BY s.key::text) AS source_keys
    FROM source_record sr JOIN source s ON s.id = sr.source_id
    WHERE sr.edition_id IS NOT NULL
    GROUP BY sr.edition_id
)
SELECT
    r.id            AS race_id,
    ed.id           AS edition_id,
    ev.id           AS event_id,
    ev.slug         AS event_slug,
    ev.name         AS event_name,
    r.name          AS race_name,
    s.slug          AS sport_slug,
    d.slug          AS discipline_slug,
    ed.year, ed.start_date, ed.end_date, r.start_time,
    v.city, v.region, v.country, v.lat, v.lon,
    r.distances,
    COALESCE(a.attributes, '{}'::jsonb) AS attributes,
    r.relay, r.team, r.participant_limit, r.participants_registered,
    COALESCE(cw.state, 'unknown') AS reg_state,
    cw.opens_at AS reg_opens_at, cw.closes_at AS reg_closes_at,
    cw.state_checked_at AS reg_checked_at,
    COALESCE(cw.url, ed.registration_url) AS registration_url,
    ed.registration_platform, ed.info_url,
    ed.status AS edition_status,
    ed.data_quality_score,
    ed.updated_at,
    pf.amount AS price_from, pf.currency,
    COALESCE(es.source_keys, ARRAY[]::text[]) AS source_keys,
    to_tsvector('simple',
        immutable_unaccent(COALESCE(ev.name, '') || ' ' || COALESCE(r.name, '') || ' ' ||
                 COALESCE(v.city, '') || ' ' || COALESCE(v.region, '') || ' ' ||
                 COALESCE(s.slug, '') || ' ' || COALESCE(d.slug, ''))
    ) AS search_vector
FROM race r
JOIN event_edition ed ON ed.id = r.edition_id
JOIN event ev         ON ev.id = ed.event_id
JOIN sport s          ON s.id = ev.sport_id
JOIN discipline d     ON d.id = r.discipline_id
LEFT JOIN venue v     ON v.id = ed.venue_id
LEFT JOIN current_window cw ON cw.race_id = r.id
LEFT JOIN price_from pf     ON pf.registration_window_id = cw.window_id
LEFT JOIN attrs a           ON a.race_id = r.id
LEFT JOIN edition_sources es ON es.edition_id = ed.id
WHERE ev.status = 'published'
"""

INDEXES_V2 = [
    "CREATE UNIQUE INDEX race_search_race_id_idx ON race_search (race_id)",
    "CREATE INDEX race_search_start_date_idx ON race_search (start_date)",
    "CREATE INDEX race_search_sport_idx ON race_search (sport_slug, discipline_slug)",
    "CREATE INDEX race_search_country_idx ON race_search (country)",
    "CREATE INDEX race_search_fts_idx ON race_search USING GIN (search_vector)",
    "CREATE INDEX race_search_name_trgm_idx ON race_search USING GIN (event_name gin_trgm_ops)",
    "CREATE INDEX race_search_attrs_idx ON race_search USING GIN (attributes jsonb_path_ops)",
    "CREATE INDEX race_search_sources_idx ON race_search USING GIN (source_keys)",
]


def upgrade() -> None:
    # 0001 builds tables from the ORM metadata, so on a fresh database this table may exist
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geocode_cache (
            query TEXT PRIMARY KEY,
            provider VARCHAR(32) NOT NULL,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            display_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS source_record_edition_idx ON source_record (edition_id)"
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS race_search")
    op.execute(RACE_SEARCH_VIEW_V2)
    for stmt in INDEXES_V2:
        op.execute(stmt)


def downgrade() -> None:
    from importlib import util
    from pathlib import Path

    spec = util.spec_from_file_location("rev0001", Path(__file__).with_name("0001_initial.py"))
    assert spec and spec.loader
    rev0001 = util.module_from_spec(spec)
    spec.loader.exec_module(rev0001)

    op.execute("DROP MATERIALIZED VIEW IF EXISTS race_search")
    op.execute(rev0001.RACE_SEARCH_VIEW_SQL.replace("unaccent(", "immutable_unaccent("))
    for stmt in rev0001.RACE_SEARCH_INDEXES_SQL:
        op.execute(stmt)
    op.execute("DROP INDEX IF EXISTS source_record_edition_idx")
    op.execute("DROP TABLE IF EXISTS geocode_cache")
