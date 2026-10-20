# Sports Events Hub — Implementation Plan

**Status:** v1.0 (planning) · **Date:** 2026-10-18 · **Owner:** Igor Quaresma
**Repo:** `sports-events-hub` · **Backend:** Python / FastAPI · **Frontend:** Next.js (TypeScript) · **DB:** PostgreSQL

This document is the single source of truth for building the Sports Events Hub. It is written so that each section can be handed to a developer (or a coding agent) as a self-contained work package. Decisions are recorded in §12 and should be appended to as the project evolves.

---

## Table of contents

1. [Vision, scope and MVP boundaries](#1-vision-scope-and-mvp-boundaries)
2. [High-level architecture and tech stack](#2-high-level-architecture-and-tech-stack)
3. [Data model and PostgreSQL schema](#3-data-model-and-postgresql-schema)
4. [Data acquisition: sources, connectors, normalization, dedup](#4-data-acquisition)
5. [Backend API design and search](#5-backend-api-design-and-search)
6. [Frontend design and UX flows](#6-frontend-design-and-ux-flows)
7. [AI features](#7-ai-features)
8. [Registration flow and partner integration](#8-registration-flow-and-partner-integration)
9. [Security, privacy and legal](#9-security-privacy-and-legal)
10. [Engineering practices, testing, CI/CD, observability, infrastructure](#10-engineering-practices)
11. [Phased roadmap](#11-phased-roadmap)
12. [Risks, open questions, decision log](#12-risks-open-questions-and-decision-log)
- [Appendix A — Repository layout](#appendix-a--repository-layout)
- [Appendix B — Environment variables](#appendix-b--environment-variables)
- [Appendix C — Example API payloads](#appendix-c--example-api-payloads)
- [Appendix D — Sources consulted](#appendix-d--sources-consulted)

---

## 1. Vision, scope and MVP boundaries

### 1.1 Vision

One place where an athlete types what they want ("Olympic-distance triathlon in Germany in May, wetsuit allowed, flat bike course") and gets back the matching events, a trustworthy summary of each one, the current registration status, and a one-click path to the official registration page. The hub does **not** replace organizers' registration systems; it makes events *findable* and *comparable*, and it tracks the user's intent so it can remind them before deadlines.

### 1.2 Core user stories (MVP)

| ID | As a… | I want to… | So that… |
|----|-------|-----------|----------|
| U1 | Athlete | search events by sport, discipline/distance, country/region, date range, and race conditions | I find races that fit my goals |
| U2 | Athlete | type a free-text query in natural language | I don't have to learn the filter UI |
| U3 | Athlete | see a compact, reliable summary per event (date, location, distances, price, registration window, course profile, cut-offs) | I can compare quickly |
| U4 | Athlete | open the official registration page in one click | I can register with the organizer |
| U5 | Athlete | save events / searches and get alerts (registration opens, price tier changes, deadline near, sold out) | I never miss a race |
| U6 | Athlete | see the data's provenance and freshness ("from organizer site, checked 3 h ago") | I can trust it |
| U7 | Organizer | claim/submit my event and correct data | my event is well represented |
| U8 | Admin | monitor sources, review dedup conflicts, moderate submissions | data quality stays high |

### 1.3 MVP scope

- **Geography:** Germany, Austria, Switzerland (DACH). Data model is country-agnostic from day one.
- **Sports (MVP):** triathlon (all distances incl. relays), running (5 km, 10 km, half, marathon, ultra), trail running, cycling (road, gran fondo, gravel, MTB marathons), swimming (open water, ultra/marathon swims), obstacle course racing (OCR), HYROX, long-distance hiking events. Sport taxonomy is data-driven (§3) so new sports are configuration, not code.
- **Registration:** outbound deep-link to official registration + status tracking + reminders. No payment processing in MVP.
- **Languages:** German and English UI; event content kept in source language with AI-translated summaries.

### 1.4 Explicitly out of scope for MVP

Payment handling, in-app registration forms, results/timing data, social features, native mobile apps (PWA instead), ticket resale.

### 1.5 Success metrics

- Coverage: ≥ 80 % of DTU/DLV-sanctioned triathlon and road-running events in DACH for the coming 12 months.
- Freshness: registration status re-checked ≤ 24 h for events opening within 60 days.
- Search quality: top-3 precision ≥ 0.8 on an internal eval set of 200 queries.
- Outbound click-through rate on event detail ≥ 25 %.

---

## 2. High-level architecture and tech stack

### 2.1 Architecture overview

```
                ┌────────────────────────────────────────────────────────┐
                │                       Clients                          │
                │   Browser (Next.js SSR/ISR + PWA)   ·   Admin UI       │
                └───────────────┬────────────────────────┬───────────────┘
                                │ HTTPS                  │
                ┌───────────────▼────────────────────────▼───────────────┐
                │        Edge: Caddy/Traefik (TLS, WAF rules, rate limit)│
                └───────────────┬────────────────────────────────────────┘
                                │
        ┌───────────────────────▼───────────────────────┐    ┌───────────────────┐
        │     API service (FastAPI, async, OpenAPI)     │◄──►│  Redis            │
        │  /v1/events /v1/search /v1/auth /v1/alerts …  │    │  cache · queues · │
        └───────┬───────────────┬───────────────┬───────┘    │  rate limits      │
                │               │               │            └─────────┬─────────┘
     ┌──────────▼─────┐  ┌──────▼──────┐  ┌─────▼──────────┐           │
     │ PostgreSQL 16  │  │ Object store│  │ LLM gateway    │           │
     │ + PostGIS      │  │ (S3/MinIO)  │  │ (Anthropic /   │           │
     │ + pgvector     │  │ raw HTML,   │  │  local models) │           │
     │ + pg_trgm/FTS  │  │ images      │  └────────────────┘           │
     └──────────▲─────┘  └──────▲──────┘                               │
                │               │                                      │
        ┌───────┴───────────────┴──────────────────────────────────────▼───┐
        │              Worker tier (Celery / arq on Redis)                 │
        │  fetchers → parsers → normalizer → entity resolution → enricher  │
        │  (geocode, AI extraction, embeddings) → publisher → alert engine │
        │  Scheduler: Celery beat (per-source cadence)                     │
        └──────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────▼───────────────────────────────────────┐
        │  External sources: organizer sites, registration platforms,   │
        │  federation calendars, APIs (World Triathlon, race result),   │
        │  organizer submissions, iCal feeds, JSON-LD on event pages    │
        └───────────────────────────────────────────────────────────────┘
```

**Style:** a modular monolith for the API (one deployable, clear internal package boundaries) plus a separate worker deployable sharing the same codebase. This keeps operations simple while allowing extraction into services later (ingestion is the first candidate).

### 2.2 Stack decisions

| Layer | Choice | Why | Alternatives considered |
|-------|--------|-----|------------------------|
| Frontend | **Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, MapLibre GL, next-intl** | SSR/ISR for SEO (event pages are the main organic traffic driver), strong ecosystem, PWA-ready | SvelteKit (smaller ecosystem), Nuxt |
| Backend API | **FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic** | Type-safe, async, auto OpenAPI, best Python fit for scraping + AI tooling | Django/DRF (heavier, sync-first), Litestar |
| Workers | **Celery 5 + Celery beat (Redis broker)**; `arq` acceptable if staying fully async | Mature scheduling, retries, routing per source | Temporal (more power, more ops), Prefect/Dagster (data-pipeline oriented; keep in mind for later) |
| Scraping | **httpx + selectolax/BeautifulSoup** for static pages; **Playwright (Python)** only for JS-heavy pages; **Scrapy** optional for large crawls | Cheap by default, heavy only when needed | — |
| Database | **PostgreSQL 16 + PostGIS + pgvector + pg_trgm** | One engine for relational, geo, vector and full-text; you already know PostgreSQL well | Elasticsearch/OpenSearch (add later only if FTS limits are hit), Meilisearch |
| Cache / queue | **Redis 7** | Caching, Celery broker, rate limiting, pub/sub for alerts | RabbitMQ |
| Object storage | **S3-compatible (MinIO self-hosted or Hetzner Object Storage)** | Raw HTML snapshots for provenance and reprocessing, images | — |
| Auth | **Backend-owned: email+password (argon2), OAuth/OIDC (Google, Apple) via Authlib, short-lived JWT access + rotating refresh tokens in httpOnly cookies; passkeys in phase 3** | Full control, GDPR-friendly, no vendor lock-in | Keycloak/Ory (overkill for MVP), Clerk/Auth0 (data leaves EU) |
| AI | **Anthropic Claude via an internal "LLM gateway" module**; embeddings via a multilingual model (e.g. `multilingual-e5-large` self-hosted or hosted equivalent); optional local models via Ollama/vLLM for cheap bulk tasks | Structured outputs, long context for page extraction, swap-ability | OpenAI, Mistral (EU-hosted option) |
| Infra | **Docker Compose (dev) → Hetzner Cloud VMs or Hetzner + Kubernetes (k3s) later**, Caddy reverse proxy, EU region | Cost, GDPR data residency | Fly.io, AWS eu-central-1 |
| Observability | **OpenTelemetry → Grafana stack (Tempo/Loki/Prometheus) or Grafana Cloud; Sentry for errors** | Standard, vendor-neutral | Datadog |
| CI/CD | **GitHub Actions** | Repo is on GitHub (assumed) | GitLab CI |

### 2.3 Core cross-cutting principles

1. **Provenance everywhere.** Every published fact carries `source_id`, `fetched_at`, and `confidence`. Raw inputs are stored immutably.
2. **Idempotent pipelines.** Every pipeline step can be re-run safely from stored raw data.
3. **Schema-first.** Pydantic models define the canonical event schema; the API, DB, and AI extraction all validate against it.
4. **Humans in the loop.** Low-confidence AI output or dedup conflicts land in a review queue; nothing low-confidence is auto-published.
5. **Respect sources.** robots.txt, rate limits, caching, attribution and link-back are non-negotiable (§9.4).

---

## 3. Data model and PostgreSQL schema

### 3.1 Conceptual model

```
Sport ──< Discipline (e.g. Triathlon → Olympic, 70.3, Sprint; Running → 10K, Marathon)
Organizer ──< Event (the recurring thing: "Hamburg Triathlon")
Event ──< EventEdition (a dated occurrence: "Hamburg Triathlon 2027")
EventEdition ──< Race (one startable category: "Olympic distance, individual")
Race ──< RegistrationWindow (opens/closes, waitlist, sold out) ──< PriceTier
EventEdition ── Venue (PostGIS point + address) 
EventEdition ──< SourceRecord (raw + parsed snapshots from each Source)
Race ──< RaceAttribute (key/value: wetsuit_rule, elevation_gain_m, surface, draft_legal, cutoff…)
User ──< SavedEvent, SavedSearch, Alert, RegistrationIntent, OutboundClick
```

**Why Event vs. EventEdition vs. Race?** Searches are on races (distance, conditions), alerts are on editions (dates/registration), SEO pages and dedup are on events (stable identity across years).

### 3.2 Tables (DDL sketch)

Conventions: `uuid` PKs (`gen_random_uuid()`), `created_at/updated_at timestamptz` on every table, soft delete via `deleted_at` where user data is involved, all text in UTF-8, money as `numeric(10,2)` + ISO currency code.

```sql
-- Taxonomy (data-driven, editable by admins)
CREATE TABLE sport (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL,            -- 'triathlon', 'running', 'hyrox'
  name_i18n jsonb NOT NULL              -- {"de": "Triathlon", "en": "Triathlon"}
);
CREATE TABLE discipline (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sport_id uuid NOT NULL REFERENCES sport(id),
  slug text NOT NULL,                   -- 'olympic', 'half-ironman', 'marathon', 'hyrox-pro'
  name_i18n jsonb NOT NULL,
  canonical_distances jsonb,            -- {"swim_m":1500,"bike_km":40,"run_km":10}
  UNIQUE (sport_id, slug)
);

-- Organizations and sources
CREATE TABLE organizer (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL, website text, email text, country char(2),
  claimed_by_user_id uuid NULL,
  verified boolean NOT NULL DEFAULT false
);
CREATE TABLE source (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('api','feed','scrape','submission','manual')),
  name text NOT NULL, base_url text,
  connector text NOT NULL,              -- python dotted path of the connector class
  schedule_cron text, robots_policy jsonb, rate_limit_rps numeric(6,2) DEFAULT 0.5,
  trust_score smallint NOT NULL DEFAULT 50,   -- 0..100, feeds precedence rules
  enabled boolean NOT NULL DEFAULT true,
  last_run_at timestamptz, last_success_at timestamptz, last_error text
);

-- Core entities
CREATE TABLE event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL,            -- 'hamburg-triathlon'
  name text NOT NULL,
  sport_id uuid NOT NULL REFERENCES sport(id),
  organizer_id uuid REFERENCES organizer(id),
  website text,
  description_i18n jsonb,               -- AI/human summaries per language
  status text NOT NULL DEFAULT 'published' CHECK (status IN ('draft','review','published','archived')),
  search_vector tsvector,               -- maintained by trigger
  embedding vector(1024)                -- pgvector, semantic search
);
CREATE TABLE venue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text, street text, postal_code text, city text, region text, country char(2) NOT NULL,
  geom geography(Point, 4326) NOT NULL,
  geocode_source text, geocode_confidence real
);
CREATE TABLE event_edition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
  year smallint NOT NULL,
  start_date date NOT NULL, end_date date,
  venue_id uuid REFERENCES venue(id),
  registration_url text,                -- the official registration link (deep link)
  info_url text,
  registration_platform text,           -- 'raceresult','datasport','organizer','ahotu',...
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','cancelled','postponed','finished')),
  summary_i18n jsonb,                   -- AI-generated, reviewed summary
  data_quality_score real,              -- 0..1 completeness/consistency
  last_verified_at timestamptz,
  UNIQUE (event_id, year, start_date)
);
CREATE TABLE race (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edition_id uuid NOT NULL REFERENCES event_edition(id) ON DELETE CASCADE,
  discipline_id uuid NOT NULL REFERENCES discipline(id),
  name text NOT NULL,                   -- 'Olympic Distance Individual'
  start_time timestamptz,
  distances jsonb,                      -- {"swim_m":1500,"bike_km":40,"run_km":10}
  participant_limit int, participants_registered int,
  relay boolean DEFAULT false, team boolean DEFAULT false,
  age_min smallint, age_max smallint,
  license_required boolean,
  search_vector tsvector
);
CREATE TABLE race_attribute (                 -- flexible "race conditions"
  race_id uuid NOT NULL REFERENCES race(id) ON DELETE CASCADE,
  key text NOT NULL,                    -- 'wetsuit_rule','elevation_gain_m','surface','draft_legal',
                                        -- 'water_type','cutoff_minutes','course_profile','certified_course'
  value jsonb NOT NULL,
  source_record_id uuid, confidence real,
  PRIMARY KEY (race_id, key)
);
CREATE TABLE registration_window (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  race_id uuid NOT NULL REFERENCES race(id) ON DELETE CASCADE,
  opens_at timestamptz, closes_at timestamptz,
  state text NOT NULL CHECK (state IN ('not_open','open','waitlist','sold_out','closed','unknown')),
  state_checked_at timestamptz NOT NULL,
  url text
);
CREATE TABLE price_tier (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  registration_window_id uuid NOT NULL REFERENCES registration_window(id) ON DELETE CASCADE,
  label text, amount numeric(10,2) NOT NULL, currency char(3) NOT NULL,
  valid_from timestamptz, valid_until timestamptz,
  includes_license boolean
);

-- Provenance
CREATE TABLE source_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES source(id),
  external_id text,                     -- id in the source system if any
  url text NOT NULL,
  fetched_at timestamptz NOT NULL,
  http_status int, content_hash text NOT NULL,
  raw_object_key text NOT NULL,         -- S3 key of the raw HTML/JSON
  parsed jsonb,                         -- canonical EventCandidate (Pydantic) as JSON
  parse_method text,                    -- 'api','jsonld','css','llm'
  parse_confidence real,
  edition_id uuid REFERENCES event_edition(id),   -- set after entity resolution
  UNIQUE (source_id, url, content_hash)
);
CREATE TABLE field_provenance (             -- which source won for which field
  edition_id uuid NOT NULL REFERENCES event_edition(id) ON DELETE CASCADE,
  field_path text NOT NULL,             -- 'race[olympic].distances.bike_km'
  source_record_id uuid NOT NULL REFERENCES source_record(id),
  decided_at timestamptz NOT NULL, rule text,   -- 'trust_score','freshest','manual'
  PRIMARY KEY (edition_id, field_path)
);
CREATE TABLE dedup_candidate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  left_edition_id uuid NOT NULL, right_edition_id uuid NOT NULL,
  score real NOT NULL, features jsonb,
  decision text CHECK (decision IN ('pending','merged','distinct')) DEFAULT 'pending',
  decided_by uuid, decided_at timestamptz
);

-- Users and engagement
CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL, email_verified_at timestamptz,
  password_hash text,                   -- NULL for OAuth-only
  display_name text, locale text DEFAULT 'de', home_country char(2),
  role text NOT NULL DEFAULT 'athlete' CHECK (role IN ('athlete','organizer','admin')),
  consent jsonb NOT NULL DEFAULT '{}',  -- {"marketing": false, "analytics": false, "ts": ...}
  deleted_at timestamptz
);
CREATE TABLE oauth_account (user_id uuid REFERENCES app_user(id) ON DELETE CASCADE, provider text, provider_user_id text, PRIMARY KEY (provider, provider_user_id));
CREATE TABLE refresh_token (id uuid PRIMARY KEY, user_id uuid REFERENCES app_user(id) ON DELETE CASCADE, token_hash text UNIQUE NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz, user_agent text, ip inet);
CREATE TABLE saved_event (user_id uuid REFERENCES app_user(id) ON DELETE CASCADE, edition_id uuid REFERENCES event_edition(id) ON DELETE CASCADE, created_at timestamptz DEFAULT now(), PRIMARY KEY (user_id, edition_id));
CREATE TABLE saved_search (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid REFERENCES app_user(id) ON DELETE CASCADE, name text, query jsonb NOT NULL, alert_enabled boolean DEFAULT true);
CREATE TABLE alert (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('registration_opens','deadline_near','price_tier_change','sold_out','new_match','date_change')),
  edition_id uuid, saved_search_id uuid,
  channel text NOT NULL DEFAULT 'email', state text DEFAULT 'active',
  last_sent_at timestamptz
);
CREATE TABLE registration_intent (      -- user says "I plan to / I have registered"
  user_id uuid REFERENCES app_user(id) ON DELETE CASCADE,
  race_id uuid REFERENCES race(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('interested','registered','done','withdrawn')),
  updated_at timestamptz DEFAULT now(), PRIMARY KEY (user_id, race_id)
);
CREATE TABLE outbound_click (id bigserial PRIMARY KEY, edition_id uuid, user_id uuid NULL, target_url text NOT NULL, ts timestamptz DEFAULT now(), anon_session_hash text);
CREATE TABLE audit_log (id bigserial PRIMARY KEY, actor_id uuid, action text, entity text, entity_id uuid, diff jsonb, ts timestamptz DEFAULT now());
```

### 3.3 Indexes

```sql
CREATE INDEX ON event_edition (start_date);
CREATE INDEX ON event_edition (event_id, year);
CREATE INDEX ON race (edition_id); CREATE INDEX ON race (discipline_id);
CREATE INDEX venue_geom_gix ON venue USING GIST (geom);
CREATE INDEX event_fts ON event USING GIN (search_vector);
CREATE INDEX race_fts ON race USING GIN (search_vector);
CREATE INDEX event_name_trgm ON event USING GIN (name gin_trgm_ops);         -- fuzzy/typo-tolerant
CREATE INDEX event_embedding_hnsw ON event USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON registration_window (race_id, state);
CREATE INDEX ON source_record (source_id, fetched_at DESC);
CREATE INDEX ON race_attribute USING GIN (value jsonb_path_ops);
```

A materialized view `race_search` (race + edition + event + venue + current registration window + flattened attributes) is refreshed by the publisher step and is what `/v1/search` queries. This keeps query plans simple and fast.

### 3.4 Canonical Pydantic schema (shared by API, ingestion and AI)

```python
class RaceCandidate(BaseModel):
    name: str
    discipline_slug: str                      # must exist in taxonomy
    start_time: datetime | None
    distances: dict[str, float] = {}          # swim_m, bike_km, run_km, total_km, elevation_gain_m
    attributes: dict[str, Any] = {}           # wetsuit_rule, surface, draft_legal, cutoff_minutes...
    participant_limit: int | None = None
    registration: RegistrationCandidate | None = None

class EventCandidate(BaseModel):
    name: str
    sport_slug: str
    start_date: date
    end_date: date | None = None
    location: LocationCandidate                 # free text + optional lat/lon, country
    organizer_name: str | None = None
    website: HttpUrl | None = None
    registration_url: HttpUrl | None = None
    registration_platform: str | None = None
    races: list[RaceCandidate]
    description: str | None = None
    language: str = "de"
    source_url: HttpUrl
    external_id: str | None = None
    evidence: dict[str, str] = {}             # field -> quoted snippet from the page (for AI extraction)
```

---

## 4. Data acquisition

### 4.1 Source landscape (DACH, MVP sports)

| Source | Type | What it gives | Access method | Notes |
|--------|------|---------------|---------------|-------|
| World Triathlon Events API (`developers.triathlon.org`) | API | Sanctioned triathlon calendar incl. Europe; events, search | Registered app + key; rate limits documented per app | Good seed for triathlon; licensing terms to be checked |
| race result (`my.raceresult.com`) | Per-event static API + public event pages | Participant counters, settings (name, date, location), lists | "Simple API" static links per event, no public event directory; 1 call/s per URL, cached 10–30 s | Discover events via organizer pages, then use event IDs; many DACH organizers use it for registration |
| DTU / Landesverbände (German Triathlon Union) | Web calendar | Sanctioned triathlons in Germany | Scrape (respect ToS) or request data partnership | Authoritative for Germany |
| DLV Laufkalender / regional LV calendars | Web calendar | Road running, certified courses | Scrape or partnership | Authoritative for certified distances |
| Datasport (CH) | Registration platform | Swiss running/triathlon/cycling events | Scrape public calendar; ask for feed | Dominant in Switzerland |
| Ahotu, hdsports, laufen.de, runme, triathlon-szene | Aggregators | Broad calendars | Scrape only with permission or use as *discovery* (URLs) not content | Aggregators' ToS often forbid reuse → treat as link discovery only |
| HYROX (hyrox.com) | Organizer site | Official season calendar, ticketing links | Scrape calendar page; JSON-LD likely absent | Single source, high value |
| Organizer websites | Web | Ground truth: course, rules, prices, registration link | JSON-LD `schema.org/SportsEvent` where present; CSS/LLM extraction otherwise | Thousands of long-tail sites; LLM extraction shines here |
| Organizer submissions | Form | Events submitted/claimed by organizers | Web form + moderation | Highest trust once verified |
| iCal / RSS feeds | Feed | Some clubs/federations publish calendars | `icalendar` parser | Cheap and reliable when available |
| Sitemaps + search discovery | Discovery | New event URLs | Sitemap parsing; search API (e.g. Brave/SerpAPI) for "triathlon anmeldung 2027" | Feeds the discovery queue only |

Priority order: (1) federation calendars + World Triathlon API for *coverage*, (2) organizer sites for *truth*, (3) registration platforms for *status*, (4) submissions for *corrections*.

### 4.2 Pipeline stages

```
discover → fetch → store raw → parse → normalize → resolve (dedup/merge) → enrich → validate → publish → notify
```

| Stage | Responsibility | Implementation |
|-------|----------------|----------------|
| **Discover** | Produce candidate URLs/IDs per source | Connector `discover()` yields `DiscoveredItem(url, external_id, hint)`; dedup against `source_record.url` |
| **Fetch** | Download politely | `httpx.AsyncClient` with per-host token bucket (Redis), `robots.txt` cache (`protego`), ETag/If-Modified-Since, retries with jitter, 10 s timeouts, max 2 MB body, SSRF guard (deny private IPs, only http/https); Playwright pool for allow-listed JS sites |
| **Store raw** | Immutable evidence | Write body to S3 `raw/{source}/{yyyy}/{mm}/{sha256}.html`; insert `source_record` with `content_hash`; skip downstream if hash unchanged |
| **Parse** | Raw → `EventCandidate` | Strategy chain: API JSON → JSON-LD (`extruct`) → source-specific CSS parser → LLM extraction (§7.3). Each parser returns candidate + method + confidence |
| **Normalize** | Canonical units, taxonomy mapping, dates | Distances to m/km; discipline classifier (rules first: "Olympische Distanz", "1.5/40/10" → `olympic`; LLM fallback); timezone from venue; currency from country; text cleanup |
| **Resolve** | Entity resolution across sources | Blocking by (sport, start_date ± 3 days, country) + geo within 25 km → scoring: name similarity (trigram + token set), venue distance, same registration URL domain, organizer match → auto-merge ≥ 0.92, review queue 0.7–0.92, distinct < 0.7. Field-level merge by `source.trust_score` then freshness; record `field_provenance` |
| **Enrich** | Geocode, embeddings, summaries, translations | Nominatim (self-hosted) or Photon for geocoding with cache; embeddings on `name + summary + attributes`; AI summary (§7.4) |
| **Validate** | Business rules | Dates in future or ≤ 2 years past; distances within discipline tolerance; registration closes ≥ opens; URL reachable; compute `data_quality_score` |
| **Publish** | Make visible | Upsert into core tables, refresh `race_search` MV (concurrently), invalidate caches, emit `EditionChanged` event |
| **Notify** | Alerts | Alert engine consumes change events and matches alerts/saved searches (§5.6) |

### 4.3 Connector interface

```python
class Connector(Protocol):
    source_key: str
    async def discover(self, ctx: RunContext) -> AsyncIterator[DiscoveredItem]: ...
    async def fetch(self, item: DiscoveredItem, ctx: RunContext) -> RawDocument: ...
    def parse(self, raw: RawDocument) -> list[ParseResult]: ...   # pure, testable with fixtures
```

Each connector lives in `backend/app/ingestion/connectors/<source>/` with `fixtures/` (saved HTML/JSON) and tests asserting the parsed `EventCandidate`. Connectors are registered in the `source` table by dotted path, so enabling a source is a DB change. Adding a source = new folder + fixture tests + row in `source`.

### 4.4 Scheduling and change detection

- Celery beat reads `source.schedule_cron`; default: federation calendars daily, organizer pages weekly, **registration status pages every 6–24 h for editions starting within 90 days** (adaptive: more frequent near open/close dates).
- Change detection on `content_hash`; a semantic diff (parsed JSON diff) decides whether to re-run enrichment (expensive) or just update status (cheap).
- Backpressure: per-source concurrency limits; global budget for Playwright and LLM calls per day.

### 4.5 Optional: FME as an ingestion tool

For federation Excel/CSV exports or partner feeds, an FME workspace can emit `EventCandidate` JSON into an S3 bucket or call `POST /v1/ingest/candidates` (service token). This reuses your existing skillset without making FME a hard dependency.

---

## 5. Backend API design and search

### 5.1 Conventions

- Base path `/v1`, JSON only, snake_case, RFC 7807 problem details for errors, cursor pagination (`?cursor=&limit=`), ETags on GETs, `Accept-Language` for i18n fields, OpenAPI at `/v1/openapi.json` (generated client for the frontend via `openapi-typescript`).
- Versioning by path; breaking changes → `/v2` with deprecation headers.
- All list endpoints are read-only and cacheable (Redis, 60 s; CDN-friendly `Cache-Control`).

### 5.2 Endpoints (MVP)

| Method & path | Purpose | Auth |
|---------------|---------|------|
| `GET /v1/search` | Structured + free-text race search (§5.3) | public |
| `POST /v1/search/parse` | Natural-language query → structured filters (AI, §7.2) | public, rate-limited |
| `GET /v1/events/{slug}` | Event + editions overview | public |
| `GET /v1/editions/{id}` | Full edition detail incl. races, windows, prices, provenance | public |
| `GET /v1/editions/{id}/go` | Tracked redirect to official registration/info URL (302) | public |
| `GET /v1/taxonomy` | Sports, disciplines, attribute keys with labels | public |
| `GET /v1/geo/suggest?q=` | Place autocomplete (Photon) | public |
| `POST /v1/auth/register` · `/login` · `/logout` · `/refresh` · `/oauth/{provider}` · `/verify-email` · `/password-reset` | Auth | mixed |
| `GET/PUT /v1/me` · `DELETE /v1/me` (GDPR erasure) · `GET /v1/me/export` (GDPR access) | Profile | user |
| `GET/POST/DELETE /v1/me/saved-events` · `/saved-searches` · `/alerts` · `/intents` | Engagement | user |
| `POST /v1/organizer/claims` · `POST /v1/organizer/events` · `PUT …/{id}` | Organizer self-service | organizer |
| `GET /v1/admin/sources` · `POST …/{id}/run` · `GET /v1/admin/review/dedup` · `POST …/{id}/decide` · `GET /v1/admin/review/extractions` | Admin | admin |
| `POST /v1/ingest/candidates` | Push feed from partners/FME | service token |
| `GET /healthz` · `/readyz` · `/metrics` | Ops | internal |

### 5.3 Search semantics

Query parameters (all optional, combinable):

```
q=                      free text (hybrid search)
sport=triathlon&discipline=olympic,sprint
country=DE,AT&region=Bayern
near=48.137,11.575&radius_km=150        (PostGIS ST_DWithin)
date_from=2027-05-01&date_to=2027-06-30
reg_state=open,not_open&reg_opens_before=2027-01-31
price_max=120&currency=EUR
attr.wetsuit_rule=allowed,mandatory&attr.elevation_gain_m.lte=300&attr.surface=road
relay=true&participants_min=500
sort=relevance|date|distance|price
```

Ranking for `relevance` (hybrid): `0.45 * BM25(ts_rank_cd) + 0.35 * cosine(pgvector) + 0.10 * freshness + 0.10 * data_quality_score`, with hard filters applied in SQL first. Use Reciprocal Rank Fusion if weights prove brittle. Typos handled by `pg_trgm` similarity on names. Facet counts returned alongside results (`facets: {discipline: {...}, country: {...}, reg_state: {...}}`).

### 5.4 Internal module layout (modular monolith)

```
backend/app/
  core/        settings (pydantic-settings), logging, security, db session, redis
  domain/      pure models + business rules (no I/O)
  taxonomy/    sports/disciplines/attributes
  events/      repositories, services, API routers for events/editions/races
  search/      query builder, ranking, facets, MV refresh
  users/       auth, profile, GDPR export/erasure
  engagement/  saved items, alerts, intents, outbound tracking
  organizer/   claims, submissions, moderation
  ingestion/   connectors/, pipeline/, resolution/, enrichment/
  ai/          llm gateway, prompts, schemas, evals
  admin/       review queues, source management
  workers/     celery app, tasks, beat schedule
  api/         FastAPI app factory, routers, middleware, error handlers
```

Rule: `domain` imports nothing from other packages; `api` and `workers` are the only entry points; services depend on repository interfaces (easy to test).

### 5.5 Background jobs

`ingest.run_source`, `ingest.fetch_item`, `ingest.parse_record`, `resolve.match_edition`, `enrich.geocode`, `enrich.embed`, `enrich.summarize`, `publish.refresh_mv`, `alerts.evaluate`, `alerts.send_email`, `maintenance.purge_raw_older_than`, `maintenance.gdpr_erasure`. Each task is idempotent, has explicit retry policy, and emits OpenTelemetry spans.

### 5.6 Alert engine

Change events (`RegistrationStateChanged`, `PriceTierChanged`, `EditionPublished`, `DateChanged`) are written to an outbox table and processed by `alerts.evaluate`, which matches against `alert` and `saved_search.query` (re-run the search with `created_after`). Delivery via email (Postmark/SES in EU or self-hosted Postal), with digest batching (max 1 email/day/user unless `deadline_near`). Web push in phase 3.

---

## 6. Frontend design and UX flows

### 6.1 Pages / routes

| Route | Rendering | Purpose |
|-------|-----------|---------|
| `/` | SSR | Hero search box (free text + quick chips: sport, country, month), featured "registration opening soon" |
| `/search` | CSR with URL-synced state (SSR first paint) | Results list + map toggle, facet sidebar, sort; infinite scroll with cursor |
| `/events/[slug]` | ISR (revalidate 1 h; on-demand revalidation from publisher) | Event page: next edition summary, race table, registration box, course facts, map, provenance footer, past editions |
| `/events/[slug]/[year]` | ISR | Edition-specific page (SEO for "Hamburg Triathlon 2027") |
| `/calendar/[sport]/[country]` · `/[discipline]` | ISR | SEO landing pages (programmatic) |
| `/me`, `/me/saved`, `/me/alerts`, `/me/intents` | CSR, auth | Athlete area |
| `/organizer/*` | CSR, auth | Claim/submit/edit |
| `/admin/*` | CSR, auth | Sources, review queues, quality dashboards |
| `/login`, `/register`, `/legal/impressum`, `/legal/datenschutz`, `/legal/agb` | SSR | Auth + legal (mandatory in DE) |

### 6.2 Key UX elements

- **Search box with "understanding" preview:** after a natural-language query, show the parsed filters as removable chips ("Triathlon · Olympic · Germany · May 2027 · wetsuit allowed") so the user sees and corrects what the AI understood.
- **Race card:** name, date, city/country, discipline chips, price-from, registration state badge with checked-time, distance from user (if location allowed).
- **Registration box (detail page):** state, opens/closes, price tiers timeline, "Register on official site" primary button (tracked), "Remind me" secondary, "I've registered" toggle, add-to-calendar (.ics).
- **Provenance footer:** "Data from: organizer site (checked 3 h ago), DTU calendar (2 d ago). Report an error."
- **Map view:** MapLibre with clustered markers; draw-a-radius search.
- **Accessibility:** WCAG 2.1 AA, keyboard-complete, `prefers-reduced-motion`, color-contrast-checked badges.
- **Performance budgets:** LCP < 2.5 s on 4G, JS < 200 kB gz on search page, images via `next/image`.

### 6.3 State and data fetching

TanStack Query with the generated OpenAPI client; search state lives in the URL (shareable links); optimistic updates for save/alert actions; auth via httpOnly cookies, CSRF token header for mutations (§9.2).

### 6.4 i18n

`next-intl` with `de` default, `en` second; route prefix `/en/...`; event content fields are `*_i18n` JSON with fallback chain (requested → source language → en).

---

## 7. AI features

All AI calls go through `app/ai/gateway.py` (single place for provider choice, retries, timeouts, token/cost accounting, prompt versioning, PII scrubbing, caching by content hash). Structured outputs are always validated against Pydantic schemas; invalid output → retry once with the validation error → else fall back / queue for review. Every AI-produced field stores `model`, `prompt_version`, `confidence`, and `evidence` snippets.

| # | Feature | Phase | Model class | Design |
|---|---------|-------|-------------|--------|
| 7.1 | **Hybrid semantic search** | 2 | Embeddings (multilingual) | Embed `event.name + summary + discipline + attributes`; query embedding at request time (cached 24 h per normalized query); fused with BM25 (§5.3). German/English cross-lingual by design |
| 7.2 | **Natural-language query parsing** | 2 | Small/fast LLM (Haiku-class) | Prompt returns `SearchFilters` JSON (sport, discipline, country/region/near, date range, attributes, sort). Few-shot with DE/EN examples; unknown terms become `q` free text; show parsed chips to user. Cache by normalized query. Budget: < 300 ms p95 |
| 7.3 | **Page extraction** | 1 | Long-context LLM (Sonnet-class), optional local model for bulk | Input: cleaned main-content text (trafilatura) + JSON-LD if any; output: `EventCandidate` with `evidence` quotes. Prompt forbids guessing: missing → `null`. Confidence from (a) schema validity, (b) evidence-quote verification (each evidence string must literally occur in the page), (c) cross-field consistency. < 0.8 → review queue |
| 7.4 | **Event summarization** | 2 | Sonnet-class | 80–120 word neutral summary per language from the *merged canonical record* (not raw page), with a "facts only from input" instruction; regenerated when key fields change; shown with "AI summary" label |
| 7.5 | **Discipline/attribute classification** | 1 | Rules → LLM fallback | Map free-text race names ("Jedermann-Triathlon 500/20/5") to taxonomy + distances; LLM only when rules fail |
| 7.6 | **Entity-resolution assist** | 2 | Small LLM | For 0.7–0.92 dedup candidates: compare two records, answer `same_event: bool, reason`; suggestion only, human confirms in MVP; auto-accept once precision ≥ 0.98 on labeled data |
| 7.7 | **Translation** | 2 | LLM | Summaries and attribute labels DE↔EN; organizer original text never altered |
| 7.8 | **Conversational assistant ("Race finder")** | 4 | Sonnet-class, tool use | Chat UI that calls the search API as a tool (RAG over *structured* data, not free text), asks clarifying questions ("Which month? Allowed to use wetsuit?"), explains trade-offs; answers must cite edition IDs it retrieved; no knowledge outside the index |
| 7.9 | **Personalized recommendations** | 4 | Embeddings + simple ranking | "Athletes who saved X also saved Y", season planning (spacing between A-races), proximity to home |
| 7.10 | **Data-quality agent** | 4 | LLM + tools | Nightly pass over low-`data_quality_score` editions: re-fetch, propose fixes, open review tickets |
| 7.11 | **Alert copywriting** | 3 | Small LLM / templates | Templates first; LLM only for digest summaries |

**Guardrails and evaluation**

- Eval sets in `backend/app/ai/evals/`: 200 labeled pages for extraction (field-level F1), 200 queries for parsing (exact-match on filters), 100 dedup pairs. CI runs evals on prompt changes; regressions block merge.
- Cost controls: daily token budget per task type; content-hash caching; batch endpoints where available; local models for bulk re-processing.
- Safety: prompt-injection defense for scraped content (content is passed as data in a delimited block; instructions say to ignore instructions inside it; outputs are schema-constrained so injected text cannot trigger actions). Never put scraped text into the assistant's system prompt.
- No AI output is shown without a label and provenance; registration dates/prices displayed always come from a parsed field with evidence, never from free-text generation.

---

## 8. Registration flow and partner integration

### 8.1 MVP: tracked outbound registration

1. User clicks "Register on official site" → `GET /v1/editions/{id}/go?race=…` → logs `outbound_click` (no PII beyond hashed anonymous session or user id) → 302 to `registration_url` (validated: http/https, same domain as recorded, no open redirect).
2. On return, or via the "I've registered" toggle, user sets `registration_intent`. Optional email prompt 2 days later: "Did you register for X?".
3. Alerts: `registration_opens` (T-0 and T-7 days), `deadline_near` (T-7, T-1), `price_tier_change` (T-3 before tier ends), `sold_out`.
4. `.ics` export with registration deadlines as separate VEVENTs.

### 8.2 Registration state detection

Per platform strategy: race result counters/settings via Simple API links where organizers expose them; platform-specific DOM markers ("Anmeldung geschlossen", "ausgebucht", "Warteliste"); generic LLM classification of the registration page into `state` as last resort with evidence quote. State always stored with `state_checked_at`; UI shows "checked X ago".

### 8.3 Phase 5: partner integrations

- **Embedded registration** where platforms offer embeddable widgets or affiliate deep links (race result, Datasport, HYROX ticketing partners). Legal/commercial agreements first.
- **Organizer self-service**: claimed organizers push updates via UI or `POST /v1/ingest/candidates`; verified organizer data gets `trust_score = 100`.
- **Affiliate/referral tracking**: UTM parameters + partner click IDs on outbound links; revenue reports.
- **In-app registration** (future, only with partners' APIs): would require PCI-scoped payment provider (Stripe/Mollie, EU entity) and explicit terms; keep out until demand is proven.

---

## 9. Security, privacy and legal

### 9.1 Threat model (summary)

Assets: user accounts and emails, saved preferences, scraped corpus, API availability, brand trust. Main threats: credential stuffing, account takeover, scraping of our own data, SSRF via fetchers, prompt injection via scraped content, abuse of AI endpoints (cost), data-protection violations, legal exposure from scraping.

### 9.2 Application security controls (OWASP ASVS L2 target)

- **Auth:** argon2id password hashing; email verification; login rate limits (IP + account); breached-password check (HIBP k-anonymity); JWT access tokens (15 min, `ES256`), refresh tokens rotated and stored hashed, revocation on logout/password change; httpOnly + `Secure` + `SameSite=Lax` cookies; CSRF double-submit token for state-changing requests; OAuth with PKCE and `state`; passkeys (WebAuthn) in phase 3; admin requires TOTP 2FA.
- **Authorization:** role + ownership checks in service layer (not only routers); organizer can edit only claimed events; admin actions audited.
- **Input validation:** Pydantic on every boundary; max payload sizes; allow-listed sort/filter keys; parameterized SQL only (SQLAlchemy); no raw string formatting into queries.
- **Output:** React escapes by default; sanitize any HTML from organizers (`bleach`/DOMPurify) — prefer Markdown; strict CSP (`default-src 'self'`, nonce for scripts, map tiles allow-listed), HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`.
- **Rate limiting & abuse:** Redis token buckets per IP/user/endpoint; stricter on `/search/parse`, auth, and assistant; bot detection via behavioral limits (no third-party CAPTCHA by default; Turnstile optional).
- **Fetcher hardening (SSRF):** resolve DNS and reject private/link-local/loopback ranges before connecting; block redirects to such ranges; only `http(s)`; size and time limits; run Playwright in a separate container with no credentials and egress only to the internet.
- **Secrets:** never in repo; `.env` for dev, Docker secrets / SOPS-encrypted files or a vault in prod; rotated API keys; least-privilege DB roles (`api_rw`, `worker_rw`, `readonly`).
- **Dependencies:** `uv` lockfile, `pip-audit`, `npm audit`, Dependabot/Renovate, Trivy image scans, pinned base images, non-root containers, read-only FS where possible.
- **Logging:** structured JSON, no secrets/PII in logs (email → hashed), request IDs, retention 30 days.
- **Backups:** nightly `pg_dump` + WAL archiving (pgBackRest) to encrypted object storage; restore test monthly.

### 9.3 Privacy (GDPR / DSGVO)

- Hosting in EU (Hetzner Falkenstein/Nuremberg); DPAs with every processor (email, LLM provider, error tracking). Prefer providers with EU data residency; for LLMs use zero-retention/no-training terms.
- Data minimization: account needs only email; location is optional and processed client-side for distance unless the user opts in.
- Lawful bases documented in a Records of Processing Activities (RoPA): contract (account, alerts), legitimate interest (fraud prevention, basic analytics without cookies), consent (marketing emails, optional analytics).
- User rights endpoints: export (`/me/export` JSON) and erasure (`DELETE /me`) implemented from day one; erasure cascades and anonymizes `outbound_click`.
- Cookie-less analytics (Plausible/Umami self-hosted) → no cookie banner needed for analytics; consent UI only if third-party cookies are ever added.
- Legal pages: Impressum, Datenschutzerklärung, AGB, Widerrufsbelehrung if paid features arrive. Get a lawyer to review before launch.
- Organizer/athlete contact data from sources: do **not** store personal data scraped from pages (e.g. contact persons) beyond organizer business contact fields; no participant lists.

### 9.4 Scraping and content legality

- Obey `robots.txt`, `noindex/noarchive` hints, and explicit ToS; keep an allow/deny list per domain in `source.robots_policy`; identify with a descriptive User-Agent and contact URL; low request rates; cache aggressively.
- Store raw pages only as internal evidence (not republished). Publish **facts** (dates, distances, prices, states) and **our own summaries**; never republish organizer prose or images without permission. Facts are not copyright-protected, but the EU database right (§§ 87a ff. UrhG) protects substantial extraction from databases → avoid bulk copying of aggregator databases; use aggregators for discovery links only, prefer federations/organizers and partnerships.
- Link back prominently to the source for every event (also good for relationships with organizers).
- Provide a "remove/correct my event" channel and honor it within 48 h.
- Keep a legal review checklist in `docs/legal/` and record per-source decisions in the decision log.

---

## 10. Engineering practices

### 10.1 Repository and tooling

- Monorepo (Appendix A). Python: `uv`, `ruff` (lint+format), `mypy --strict` on `domain` and `api`, `pytest` + `pytest-asyncio`, `hypothesis` for normalizers, `factory_boy` fixtures, `testcontainers` Postgres for integration tests. TypeScript: `pnpm`, ESLint + Prettier, `vitest`, Playwright e2e, `tsc --noEmit`.
- `pre-commit` hooks (ruff, mypy, eslint, secrets scan with `gitleaks`), Conventional Commits, PR template with checklist (tests, migration, docs, security impact).
- Architecture Decision Records in `docs/adr/NNNN-title.md` (MADR format); first ADRs: stack choice, modular monolith, Postgres-only search, LLM gateway.

### 10.2 Testing strategy

| Level | Scope | Target |
|-------|-------|--------|
| Unit | domain rules, normalizers, parsers (fixture HTML → candidate), ranking math | ≥ 85 % coverage on `domain`, `ingestion/parsers`, `search` |
| Contract | OpenAPI schema snapshot; frontend generated client compiled against it in CI | breaking change = failing build |
| Integration | API + Postgres (testcontainers) + Redis; pipeline end-to-end on fixture sources | run on every PR |
| E2E | Playwright: search → detail → outbound click; register → save → alert | nightly + release |
| AI evals | extraction F1, parse accuracy, dedup precision (§7) | on prompt/model change |
| Load | k6 against `/v1/search` (p95 < 300 ms at 50 rps on 1 node) | before launch and per release |
| Security | OWASP ZAP baseline scan, dependency audits, SSRF unit tests for fetcher | weekly + PR |

### 10.3 CI/CD

GitHub Actions: `lint` → `test` (matrix backend/frontend) → `build` (multi-stage Docker, SBOM via syft, Trivy scan) → `deploy-staging` (on `main`) → manual approval → `deploy-prod` (tagged release). Migrations run as a pre-deploy job (`alembic upgrade head`), always backward-compatible (expand/contract pattern). Feature flags via a simple `feature_flag` table + env overrides.

### 10.4 Environments and infrastructure

- **Dev:** `docker compose up` (postgres+postgis+pgvector, redis, minio, mailpit, api, worker, web). Seed script creates taxonomy + 20 demo events.
- **Staging/Prod (phase 2+):** 2 Hetzner VMs (app: api+worker+web behind Caddy; data: Postgres+Redis+MinIO) with Terraform + Ansible or Hetzner-managed Postgres if available; later k3s if horizontal scaling needed. Daily snapshots, Cloudflare in front (DNS, DDoS, cache for static) is acceptable since no personal data transits except IPs (document in DSE).
- **Observability:** OpenTelemetry SDK in API and workers → Grafana (traces, logs, metrics), Sentry for exceptions, uptime checks, alerting on: source failure rate, pipeline lag, search p95, LLM spend/day, queue depth.
- **Runbooks** in `docs/runbooks/`: source outage, bad merge rollback (via `field_provenance`), restore from backup, key rotation, GDPR request handling.

### 10.5 Data quality operations

Admin dashboard: per-source success rate, items parsed, review queue sizes, editions by `data_quality_score`, stale registration states. Weekly data-quality review ritual; "report an error" button creates a ticket linked to the edition.

---

## 11. Phased roadmap

Each phase ends with a demoable milestone and a short retro. Estimates assume one experienced developer plus AI coding assistance; adjust with team size.

| Phase | Duration | Deliverables | Exit criteria |
|-------|----------|--------------|---------------|
| **0 — Foundations** | 2 weeks | Monorepo, Docker Compose, FastAPI skeleton, Next.js skeleton, DB migrations for §3, taxonomy seed, CI with lint/test/build, ADRs 1–4 | `docker compose up` serves "hello" API + web; CI green |
| **1 — Data core** | 4 weeks | Connector framework, raw store, JSON-LD + 3 connectors (World Triathlon API, HYROX calendar, one federation calendar), rule-based normalizer, LLM extraction v1 with evals, entity resolution v1 + review UI (minimal), publisher + MV | ≥ 500 DACH editions published with provenance; extraction F1 ≥ 0.85 |
| **2 — Search MVP (public beta)** | 4 weeks | `/v1/search` hybrid, NL query parsing, search UI + map, event/edition pages (ISR, SEO), outbound tracked links, registration state detection v1, summaries, legal pages, analytics, staging+prod infra | Public beta live; p95 search < 300 ms; 200-query eval top-3 ≥ 0.8 |
| **3 — Accounts & alerts** | 3 weeks | Auth (email + OAuth), saved events/searches, alert engine + email, registration intents, .ics export, GDPR export/erasure, passkeys, organizer claim flow v1 | First 100 registered users; alert delivery SLO 99 % |
| **4 — AI depth** | 4 weeks | Race-finder assistant (tool-use over search API), recommendations, translation, dedup auto-accept, data-quality agent, cost dashboards | Assistant answer accuracy ≥ 90 % on eval; LLM cost/active user within budget |
| **5 — Coverage & partners** | ongoing | 10+ more connectors (DLV, Datasport, regional federations, long-tail organizer crawl), partner embeds/affiliate links, organizer self-service v2, expansion beyond DACH (NL, FR, IT, ES) | Coverage KPI (§1.5) met; first partner agreement signed |
| **6 — Scale & hardening** | as needed | k3s, read replicas, OpenSearch if FTS limits hit, web push, native wrapper (Capacitor) if demanded | SLOs held at 10× traffic |

Work-package granularity for implementation: each table row in §4.2, §5.2, §6.1, §7 and §9.2 is intended to become one issue/ticket.

---

## 12. Risks, open questions and decision log

### 12.1 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Aggregators/platforms forbid reuse or block scraping | High | High | Discovery-only use of aggregators; prefer federations, organizers, APIs; partnerships early (Phase 1 outreach) |
| Wrong registration dates/prices shown → user trust loss | Medium | High | Evidence-backed extraction, freshness labels, "report error", conservative display when confidence < threshold |
| LLM cost grows with corpus | Medium | Medium | Hash caching, change detection, local models for bulk, budgets/alerts |
| Dedup merges distinct events | Medium | High | Conservative thresholds, review queue, field provenance enables unmerge |
| GDPR/legal gaps at launch | Medium | High | Lawyer review of DSE/AGB, RoPA, EU-only processors |
| Single-developer bus factor | High | Medium | This plan, ADRs, runbooks, high test coverage |
| SEO dependence | Medium | Medium | Programmatic landing pages + alerts (owned channel) |

### 12.2 Open questions

- [ ] Which federations will grant a data feed or partnership? (DTU, DLV, Swiss Triathlon, ÖTRV)
- [ ] World Triathlon API licensing terms for commercial use?
- [ ] Monetization model (affiliate, organizer premium listings, athlete premium alerts) — affects data-partner negotiations.
- [ ] Self-host embeddings (GPU cost) vs. hosted API (data processing agreement)?
- [ ] Brand name / domain; company entity for Impressum.

### 12.3 Decision log

| Date | Decision | Rationale | Status |
|------|----------|-----------|--------|
| 2026-10-18 | Python/FastAPI backend, Next.js frontend, PostgreSQL-only data layer (PostGIS, pgvector, FTS) | Team skills, fewest moving parts, EU hosting | accepted |
| 2026-10-18 | DACH + endurance/outdoor sports for MVP | Manageable source count, authoritative federations | accepted |
| 2026-10-18 | Registration = tracked outbound link, no payments in MVP | Legal/PCI scope, partner dependence | accepted |
| 2026-10-18 | Aggregator sites used for discovery only | EU database right, ToS | accepted |
| 2026-10-18 | All AI through internal gateway with schema validation + evals | Cost, safety, swap-ability | accepted |
| 2026-10-21 | Moved to repo `sports-events-hub`; real sources = World Triathlon (keyless mirror), RunSignup, Ticketmaster, Wikidata→JSON-LD (see `docs/DATA_SOURCES.md`) | Only open APIs with workable terms; federations/platforms need partnerships | accepted |
| 2026-10-21 | API secrets env-only, passed as `secret_params` and redacted everywhere | Keys in query strings would otherwise leak into provenance/logs | accepted |
| 2026-10-21 | UI: URL-synced filter sidebar/dialog, labelled facets, explicit loading/empty/error states, demo data labelled and hideable | UX review of the MVP | accepted |

---

## Appendix A — Repository layout

```
sports-events-hub/
├── README.md
├── docs/
│   ├── IMPLEMENTATION_PLAN.md        ← this file
│   ├── adr/
│   ├── runbooks/
│   └── legal/
├── docker-compose.yml
├── .github/workflows/{ci.yml,deploy.yml}
├── infra/                            # terraform/, ansible/, caddy/
├── backend/
│   ├── pyproject.toml  (uv)
│   ├── alembic/
│   ├── app/            (see §5.4)
│   └── tests/{unit,integration,evals}
├── frontend/
│   ├── package.json (pnpm)
│   ├── app/            (Next.js App Router)
│   ├── components/  lib/  messages/{de,en}.json
│   └── tests/{unit,e2e}
└── scripts/            seed_taxonomy.py, import_fixture_events.py
```

## Appendix B — Environment variables

```
DATABASE_URL=postgresql+asyncpg://api_rw:***@db:5432/hub
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000  S3_BUCKET=hub-raw  S3_ACCESS_KEY=  S3_SECRET_KEY=
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_es256.pem  JWT_ACCESS_TTL=900  JWT_REFRESH_TTL=2592000
OAUTH_GOOGLE_CLIENT_ID=  OAUTH_GOOGLE_CLIENT_SECRET=  OAUTH_APPLE_...
ANTHROPIC_API_KEY=  LLM_DAILY_TOKEN_BUDGET=  EMBEDDING_MODEL=  EMBEDDING_ENDPOINT=
GEOCODER_URL=https://photon.internal  EMAIL_PROVIDER=postmark  EMAIL_API_KEY=
OTEL_EXPORTER_OTLP_ENDPOINT=  SENTRY_DSN=
FETCHER_USER_AGENT="SportsEventsHubBot/1.0 (+https://<domain>/bot)"
PLAYWRIGHT_ENABLED=false  FETCH_MAX_BYTES=2000000  FETCH_TIMEOUT_S=10
FEATURE_ASSISTANT=false
```

## Appendix C — Example API payloads

`GET /v1/search?q=olympic+triathlon+germany+may&attr.wetsuit_rule=allowed`

```json
{
  "parsed_filters": {"sport": "triathlon", "discipline": ["olympic"], "country": ["DE"], "date_from": "2027-05-01", "date_to": "2027-05-31", "attributes": {"wetsuit_rule": ["allowed"]}},
  "results": [
    {
      "race_id": "…", "edition_id": "…", "event_slug": "hamburg-triathlon",
      "name": "Hamburg Triathlon 2027 – Olympic Distance",
      "start_date": "2027-05-29", "city": "Hamburg", "country": "DE",
      "distances": {"swim_m": 1500, "bike_km": 40, "run_km": 10},
      "attributes": {"wetsuit_rule": "allowed", "surface": "road", "elevation_gain_m": 120},
      "registration": {"state": "open", "closes_at": "2027-05-15T22:00:00Z", "price_from": {"amount": 95.0, "currency": "EUR"}, "checked_at": "2026-10-18T06:12:00Z"},
      "links": {"detail": "/v1/editions/…", "go": "/v1/editions/…/go?race=…"},
      "provenance": [{"source": "organizer_site", "fetched_at": "2026-10-18T06:12:00Z"}],
      "score": 0.91
    }
  ],
  "facets": {"discipline": {"olympic": 14, "sprint": 9}, "reg_state": {"open": 6, "not_open": 8}},
  "next_cursor": "…"
}
```

`POST /v1/ingest/candidates` body = `EventCandidate` (§3.4) list; response lists accepted/rejected with validation errors.

## Appendix D — Sources consulted

- race result Simple API documentation: https://www.raceresult.com/en/support/kbexport2?id=35643 (static per-event links; lists/settings/counter APIs; 1 call/s per URL; cached 10–30 s)
- World Triathlon developer portal: https://developers.triathlon.org/ (Events API, Search API, app registration, limits)
- hdsports Lauf-/Triathlonkalender (example aggregator): https://www.hdsports.org/laufen
