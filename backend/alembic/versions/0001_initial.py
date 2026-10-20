"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-18
"""

from alembic import op

from app.models import Base

# Frozen copy of the view as created by this revision (later revisions replace it).
RACE_SEARCH_VIEW_SQL = '''
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
    to_tsvector('simple',
        unaccent(COALESCE(ev.name, '') || ' ' || COALESCE(r.name, '') || ' ' ||
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
WHERE ev.status = 'published'
'''

RACE_SEARCH_INDEXES_SQL = [
    'CREATE UNIQUE INDEX race_search_race_id_idx ON race_search (race_id)',
    'CREATE INDEX race_search_start_date_idx ON race_search (start_date)',
    'CREATE INDEX race_search_sport_idx ON race_search (sport_slug, discipline_slug)',
    'CREATE INDEX race_search_country_idx ON race_search (country)',
    'CREATE INDEX race_search_fts_idx ON race_search USING GIN (search_vector)',
    'CREATE INDEX race_search_name_trgm_idx ON race_search USING GIN (event_name gin_trgm_ops)',
    'CREATE INDEX race_search_attrs_idx ON race_search USING GIN (attributes jsonb_path_ops)',
]

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # unaccent() is STABLE, which blocks its use in indexes/generated columns;
    # wrap it in an IMMUTABLE function for the materialized view's tsvector.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text AS $$
            SELECT public.unaccent('public.unaccent', $1)
        $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        """
    )

    Base.metadata.create_all(bind=op.get_bind())

    op.execute("CREATE INDEX event_edition_start_date_idx ON event_edition (start_date)")
    op.execute("CREATE INDEX race_edition_idx ON race (edition_id)")
    op.execute("CREATE INDEX event_name_trgm_idx ON event USING GIN (name gin_trgm_ops)")
    op.execute(
        "CREATE INDEX source_record_source_idx ON source_record (source_id, fetched_at DESC)"
    )
    op.execute("CREATE INDEX registration_window_race_idx ON registration_window (race_id, state)")

    op.execute(RACE_SEARCH_VIEW_SQL.replace("unaccent(", "immutable_unaccent("))
    for stmt in RACE_SEARCH_INDEXES_SQL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS race_search")
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
