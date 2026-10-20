# Data sources — open APIs for endurance & outdoor sports events

Survey done **October 2026** (endpoints probed live). Scope: participation events (triathlon, running, trail,
cycling, open water, OCR, HYROX, hiking), focus DACH. "Implemented" means a connector ships in
`backend/app/ingestion/connectors/` and an entry exists in `backend/app/ingestion/catalog.py`.

## 1. Event APIs

| Source | Access | DACH coverage | Licence / terms | Status |
|---|---|---|---|---|
| **World Triathlon** (`triathlon.org/tri-api/v1`, official `api.triathlon.org/v1`) | Public mirror: **no key**. Official API: free key (`apikey` header) via https://apps-api.triathlon.org/register | ~10–20 sanctioned events/yr (WTCS Hamburg, Europe Cups Kitzbühel/Wels, national champs, Powerman Zofingen) | World Triathlon API terms; attribute "© World Triathlon" | ✅ `world_triathlon` |
| **RunSignup** (`runsignup.com/rest/races`) | Race search is **public**; key + secret optional (higher limits) | Very low (1–5 races); strong in US/CA | RunSignup API terms | ✅ `runsignup` |
| **Ticketmaster Discovery v2** (`app.ticketmaster.com/discovery/v2`) | Free key (`apikey` query param); 5000 calls/day, 5 req/s; deep paging capped at 1000 items | HYROX, some city runs / fitness races; mostly spectator events (filtered out) | Discovery API terms; attribution required | ✅ `ticketmaster` (needs `TICKETMASTER_API_KEY`) |
| **Wikidata Query Service** (`query.wikidata.org/sparql`) | **No key**; User-Agent with contact required | ~30 recurring DACH events with official website (Berlin/Hamburg/Vienna marathons, UTMB, KnappenMan, Mozart 100…) — no future dates | **CC0** | ✅ `wikidata` (discovery → organizer JSON-LD) |
| **schema.org `SportsEvent` JSON-LD** on organizer sites | Public web pages (robots.txt respected) | Long tail; quality depends on the organizer | Organizer's site terms | ✅ `jsonld` (also used by `wikidata`) |
| **iCal feeds** (clubs, federations) | Public `.ics` URLs | Varies per feed | Feed owner's terms | ✅ `ical` |
| **race result Simple API** (`my.raceresult.com`) | Static per-event links that the **organizer** enables; no public event directory; ≤1 call/s per URL | Very common registration/timing platform in DACH | Per organizer agreement | 🔜 partner integration — needs event IDs from organizers |
| **OpenActive** (W3C open data standard, RPDE feeds) | Per-publisher feeds, often keyless | UK only today | CC BY 4.0 / CC BY-NC-SA (per feed) | ➖ connector easy to add if DACH publishers appear |
| **ACTIVE Network Activity Search v2** | Key; new keys reportedly inactive (`ERR_403_DEVELOPER_INACTIVE`) | US-centric | ACTIVE terms | ❌ not reliable |
| **Eventbrite** | Public event search removed in 2020 (only own-org events) | — | — | ❌ |
| **Strava** | No public event search (club events need OAuth per club) | — | — | ❌ |
| **TheSportsDB / football-data etc.** | Spectator leagues & fixtures | not participation events | — | ❌ out of scope |
| UTMB, ITRA, Ironman, HYROX, Datasport, ahotu | No public API; site-internal JSON only | High | ToS usually forbid reuse | ❌ use partnerships / organizer JSON-LD instead |

## 2. Enrichment APIs

| Service | Used for | Access | Licence | Status |
|---|---|---|---|---|
| **Open-Meteo** | Race-day forecast on the event page (races ≤ 16 days away) | Keyless, server-side, cached 1 h | CC BY 4.0 — attribution shown | ✅ `GET /v1/editions/{id}/weather` |
| **OpenStreetMap Nominatim** | Coordinates for venues that only have an address (needed for "near me") | Keyless; **max 1 req/s**, cache results, identify yourself | ODbL — "© OpenStreetMap contributors" | ✅ opt-in `GEOCODING_ENABLED=true` (cached in `geocode_cache`) |
| OpenStreetMap tiles | "Map" link on event pages | Plain link to openstreetmap.org (no embedded tiles, no CSP exception) | ODbL | ✅ |

## 3. How to use them

```bash
cd backend
python -m app.cli catalog          # which sources are ready / which keys are missing
python -m app.cli seed             # taxonomy + demo data + registers every ready source
python -m app.cli run-all          # fetch from every enabled source
python -m app.cli run-source world-triathlon
```

Add a key to `.env` (e.g. `TICKETMASTER_API_KEY=...`), then `python -m app.cli sync-sources` to register the
newly available source. Source configs (countries, keywords, horizon) are editable per source in the `source`
table; `sync-sources` keeps existing configs unless `--reset-config` is passed.

## 4. Rules every connector follows

- **Secrets only in the environment.** Keys are `SecretStr` settings; `add-source` rejects secret-looking config
  keys; admin output masks them. Keys that must travel in a query string (Ticketmaster, RunSignup) are passed as
  `secret_params`, so they never reach stored URLs, provenance, logs or error messages.
- **Polite fetching.** Per-source rate limit (`source.rate_limit_rps`), bounded retries honouring `Retry-After`,
  descriptive User-Agent (+ `From: CONTACT_EMAIL`), robots.txt for every web page. The only exception is the
  Wikidata SPARQL *API* endpoint, whose robots.txt targets crawlers; organizer pages it leads to are still checked.
- **SSRF-safe.** Every hop is resolved and rejected if it points to private/loopback/link-local space; credentials
  are dropped on cross-host redirects.
- **No guessing.** Missing dates/prices stay empty. Wikidata never invents an edition date — it only discovers
  official sites, which must publish the date themselves.
- **Provenance & attribution.** Each edition records which source said what and when (`source_record`), the UI
  shows it on every event, and `/sources` lists licences and attribution texts.

## 5. Known gaps

- DACH coverage from *open* APIs is thin outside triathlon. The biggest wins are federation calendars (DTU, DLV,
  Swiss Athletics) and registration platforms (race result, Datasport, mika:timing) — these need data
  partnerships, not scraping.
- Some World Triathlon listings have no venue/coordinates; enable geocoding or fix upstream.
- Most organizer websites still lack JSON-LD; `llm_fallback` in the Wikidata source (needs `ANTHROPIC_API_KEY`)
  extracts from page text with evidence checks and marks low-confidence records in the UI.
