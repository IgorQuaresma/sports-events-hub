# Sports Events Hub

Find endurance and outdoor sports events — triathlon, running, trail, cycling, open water, OCR, HYROX, hiking —
across Germany, Austria and Switzerland, with registration status, prices, race conditions and a direct, tracked
link to the **official** registration page. The hub never handles registration or payment itself.

Architecture, security model and roadmap: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).
Real data APIs and their terms: [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

```
frontend/   Next.js 15 (App Router, TypeScript, Tailwind)   → http://localhost:3000
backend/    FastAPI + SQLAlchemy 2 (async) + Alembic         → http://localhost:8000/docs
            PostgreSQL 16 (full-text, pg_trgm, lat/lon radius search)
            ingestion pipeline + connectors (World Triathlon, RunSignup, Ticketmaster, Wikidata, JSON-LD, iCal, LLM)
docs/       implementation plan, data-source survey
```

## Quick start (Docker)

```bash
cp .env.example .env            # all keys optional; see comments inside
docker compose up --build -d    # db + api (runs migrations) + web
make seed                       # taxonomy + demo events + registers the real API sources
make ingest                     # fetch real events (World Triathlon, RunSignup, Wikidata, Ticketmaster*)
open http://localhost:3000
```

\* Ticketmaster needs a free `TICKETMASTER_API_KEY`; `make sources` shows what is ready. Real and demo data
coexist — demo events are labelled everywhere and can be hidden with the "Hide demo data" filter
(or seed without them: `python -m app.cli seed --no-sample`).

## Quick start (local dev, no Docker for app code)

Requires Python 3.12+, Node 22+, [uv](https://docs.astral.sh/uv/) and PostgreSQL 16 at `DATABASE_URL`
(e.g. `docker compose up -d db`).

```bash
# backend
cd backend
uv venv .venv && uv pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hub
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli seed                     # taxonomy, demo events, real sources
.venv/bin/python -m app.cli run-all                  # real events from the APIs
.venv/bin/uvicorn app.main:app --reload --port 8000  # API + Swagger at /docs

# frontend (second terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

## What's in the app

| Area | Details |
|------|---------|
| **Search UX** | Natural-language search turned into removable filter chips; filter sidebar (mobile: dialog) with live counts — sport, distance/format, date presets + custom range, registration status, country, *near me* + radius, max price, data source, hide demo data; URL-synced state (shareable, back button works); skeletons, empty-state suggestions, retry on errors; accessible (labels, fieldsets, focus styles, skip link, colour-independent status badges, reduced motion) |
| **Event page** | Key facts header, Register / Add to calendar (.ics) / Website / Share, races with distances, conditions and price tiers, sticky registration box, race-day weather (Open-Meteo), provenance + data completeness, schema.org JSON-LD |
| **Real data** | `world-triathlon` (keyless), `runsignup` (keyless), `wikidata` (keyless discovery → organizer JSON-LD), `ticketmaster` (key) — plus `jsonld`, `ical`, `llm_page` for any organizer site or feed |
| **Pipeline** | discover → fetch (robots.txt, per-source rate limit, retries, SSRF guard) → raw snapshot → parse → normalize → optional geocoding → entity resolution → publish → refresh search view |
| **API** | `GET /v1/search` (+ `source`, `include_demo`, source facet), `POST /v1/search/parse` (rate-limited), `GET /v1/events/{slug}`, `GET /v1/editions/{id}/go` · `/calendar.ics` · `/weather`, `GET /v1/sources`, admin + ingest (service token) |
| **Tests** | 67 backend tests (connectors against recorded API shapes, security helpers, API against Postgres); frontend typecheck, lint, build |

## Data sources

```bash
python -m app.cli catalog            # ready / missing credentials per built-in source
python -m app.cli sync-sources       # register newly available sources after adding a key
python -m app.cli run-source wikidata
python -m app.cli list-sources       # last run, last error
```

Add your own source (credentials always go in `.env`, never in `--config`):

```bash
python -m app.cli add-source hamburg-tri "Hamburg Triathlon site" --connector jsonld --kind scrape \
  --config '{"urls": ["https://example-organizer.de/anmeldung"], "sport_slug": "triathlon", "country": "DE"}'
python -m app.cli add-source lv-kalender "Landesverband Kalender" --connector ical --kind feed \
  --config '{"url": "https://example-verband.de/kalender.ics", "sport_slug": "running", "country": "DE"}'
```

Push events from FME or any script:

```bash
curl -X POST "localhost:8000/v1/ingest/candidates?source_key=fme" \
  -H "Authorization: Bearer $SERVICE_TOKEN" -H "content-type: application/json" \
  -d @candidates.json      # JSON list of EventCandidate (backend/app/schemas/candidate.py), max 500
```

## Development

```bash
make test                 # backend tests (DATABASE_URL_TEST, default postgres://…/hub_test)
make lint                 # ruff + tsc + eslint
cd frontend && npm run build
```

Migrations: `cd backend && .venv/bin/alembic revision -m "..."`, then `alembic upgrade head`. Migrations embed
frozen copies of the `race_search` view SQL; the current definition lives in `app/search/sql.py`.

## Demo data

`python -m app.cli seed` loads `backend/data/fixtures/sample_events.json`: ~90 fictional events (104 editions,
~280 races) in real DACH cities covering every sport, discipline and registration state. They are attributed to
the `sample` source, labelled "Demo data" in the UI and excluded from search-engine indexing.
Regenerate with `python scripts/make_fixture.py`; wipe event data with `python -m app.cli reset-data --yes`.

## Security

- Secrets only via environment (`SecretStr`); production refuses default `SERVICE_TOKEN` / `CLICK_HASH_SALT`
  and wildcard CORS. API keys never reach stored URLs, logs, provenance or admin output (redaction + tests).
- SSRF-hardened fetcher (every hop checked, credentials dropped on cross-host redirects), size/time limits,
  robots.txt, per-source rate limits; fixed hosts for weather/geocoding.
- Strict input validation (bad filters → 422, length and list limits), rate-limited NL parser, request size cap
  on ingest; constant-time service-token check.
- Headers: CSP (API `default-src 'none'`; web locked to self + API), HSTS in prod, `nosniff`, `frame-ancestors
  'none'`, COOP, Permissions-Policy, `no-referrer` on outbound redirects.
- Privacy: no accounts or tracking cookies; outbound clicks hashed with a secret, daily-rotating salt; geolocation
  rounded to ~1 km client-side and never stored.
- Supply chain: pinned, patched Next.js/React; `npm audit` (prod) and `pip-audit` in CI. Remaining dev-only
  advisories come from Tailwind 3's build tooling (fix requires Tailwind 4).
- Before a public launch: real Impressum/Datenschutz, edge rate limiting, CSP nonces, secrets manager — plan §9.
