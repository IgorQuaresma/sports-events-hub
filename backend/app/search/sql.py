"""SQL for the denormalized `race_search` materialized view (current version).

One row per race, joined with its edition, event, venue, current registration window,
flattened attributes and the keys of the sources that reported it. `/v1/search` queries only
this view; the publisher refreshes it. Migrations embed frozen copies of earlier versions.
"""

RACE_SEARCH_VIEW_SQL = """
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
LEFT JOIN edition_sources es ON es.edition_id = ed.id
WHERE ev.status = 'published'
"""

RACE_SEARCH_INDEXES_SQL = [
    "CREATE UNIQUE INDEX race_search_race_id_idx ON race_search (race_id)",
    "CREATE INDEX race_search_start_date_idx ON race_search (start_date)",
    "CREATE INDEX race_search_sport_idx ON race_search (sport_slug, discipline_slug)",
    "CREATE INDEX race_search_country_idx ON race_search (country)",
    "CREATE INDEX race_search_fts_idx ON race_search USING GIN (search_vector)",
    "CREATE INDEX race_search_name_trgm_idx ON race_search USING GIN (event_name gin_trgm_ops)",
    "CREATE INDEX race_search_attrs_idx ON race_search USING GIN (attributes jsonb_path_ops)",
    "CREATE INDEX race_search_sources_idx ON race_search USING GIN (source_keys)",
]

REFRESH_RACE_SEARCH_SQL = "REFRESH MATERIALIZED VIEW CONCURRENTLY race_search"
