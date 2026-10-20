/** Typed client for the Sports Events Hub API (mirrors backend/app/schemas). */

export type AttributeFilter = { key: string; op: "eq" | "in" | "lte" | "gte"; value: unknown };

export type SearchFilters = {
  q?: string | null;
  sport: string[];
  discipline: string[];
  country: string[];
  region?: string | null;
  near_lat?: number | null;
  near_lon?: number | null;
  radius_km?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  reg_state: string[];
  price_max?: number | null;
  relay?: boolean | null;
  attributes: AttributeFilter[];
  source: string[];
  include_demo: boolean;
  sort: "relevance" | "date" | "distance" | "price";
  limit: number;
  offset: number;
};

export type SearchHit = {
  race_id: string;
  edition_id: string;
  event_slug: string;
  event_name: string;
  race_name: string;
  sport_slug: string;
  discipline_slug: string;
  start_date: string;
  end_date: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  lat: number | null;
  lon: number | null;
  distance_km: number | null;
  distances: Record<string, number>;
  attributes: Record<string, unknown>;
  relay: boolean;
  reg_state: string;
  reg_opens_at: string | null;
  reg_closes_at: string | null;
  reg_checked_at: string | null;
  price_from: string | null;
  currency: string | null;
  registration_url: string | null;
  info_url: string | null;
  source_keys: string[];
  score: number | null;
};

export type SearchResponse = {
  filters: SearchFilters;
  total: number;
  results: SearchHit[];
  facets: Record<string, Record<string, number>>;
};

export type ParsedQuery = { filters: SearchFilters; chips: string[]; method: "rules" | "llm" };

export type PriceTier = {
  label: string | null; amount: string; currency: string; valid_from: string | null; valid_until: string | null;
};
export type RegistrationWindow = {
  state: string; opens_at: string | null; closes_at: string | null; state_checked_at: string; url: string | null;
  price_tiers: PriceTier[];
};
export type Race = {
  id: string; name: string; discipline_slug: string; start_time: string | null; distances: Record<string, number>;
  attributes: Record<string, unknown>; participant_limit: number | null; participants_registered: number | null;
  relay: boolean; team: boolean; registration: RegistrationWindow | null;
};
export type Provenance = {
  source_key: string; source_name: string; source_kind: string; url: string; fetched_at: string;
  parse_method: string | null; parse_confidence: number | null;
};
export type Venue = {
  name: string | null; street: string | null; postal_code: string | null; city: string | null; region: string | null;
  country: string; lat: number | null; lon: number | null;
};
export type Edition = {
  id: string; year: number; start_date: string; end_date: string | null; status: string; venue: Venue | null;
  registration_url: string | null; info_url: string | null; registration_platform: string | null; summary: string | null;
  data_quality_score: number | null; last_verified_at: string | null; races: Race[]; provenance: Provenance[];
};
export type EventDetail = {
  id: string; slug: string; name: string; sport_slug: string; website: string | null; organizer_name: string | null;
  description: string | null; is_demo: boolean;
  editions: { id: string; year: number; start_date: string; status: string; city: string | null; country: string | null }[];
  next_edition: Edition | null;
};
export type Taxonomy = {
  sports: { slug: string; name: Record<string, string>; disciplines: { slug: string; name: Record<string, string>; distances: Record<string, number> | null }[] }[];
  attributes: Record<string, { label: Record<string, string>; values?: unknown[]; numeric?: boolean }>;
  countries: Record<string, string>;
  registration_states: string[];
};
export type Weather = {
  available: boolean; reason: string | null; date: string | null; summary: string | null; weather_code: number | null;
  temp_max_c: number | null; temp_min_c: number | null; precipitation_probability_pct: number | null;
  wind_max_kmh: number | null; attribution: string; attribution_url: string;
};
export type DataSource = {
  key: string; name: string; kind: string; homepage: string | null; license: string | null; attribution: string | null;
  is_demo: boolean; editions: number; last_success_at: string | null;
};
export type Sources = {
  sources: DataSource[];
  enrichment: { key: string; name: string; purpose: string; homepage: string; license: string; attribution: string }[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** Browser calls go to the public URL; server components can use an internal one (docker network). */
export function apiBase(): string {
  if (typeof window === "undefined") {
    return process.env.API_URL_INTERNAL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/** Public base for links the user's browser follows (redirects, downloads). */
function publicBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

const TIMEOUT_MS = 10_000;

async function getJson<T>(path: string, init?: RequestInit & { next?: { revalidate?: number } }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(TIMEOUT_MS),
      headers: { accept: "application/json", ...(init?.headers || {}) },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "The event service is not reachable right now.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const api = {
  search: (params: URLSearchParams, signal?: AbortSignal) =>
    getJson<SearchResponse>(`/v1/search?${params.toString()}`, { cache: "no-store", signal }),
  parse: (query: string) =>
    getJson<ParsedQuery>(`/v1/search/parse`, {
      method: "POST", body: JSON.stringify({ query }), headers: { "content-type": "application/json" },
    }),
  event: (slug: string) => getJson<EventDetail>(`/v1/events/${encodeURIComponent(slug)}`, { next: { revalidate: 300 } }),
  taxonomy: () => getJson<Taxonomy>(`/v1/taxonomy`, { next: { revalidate: 3600 } }),
  sources: () => getJson<Sources>(`/v1/sources`, { next: { revalidate: 300 } }),
  weather: (editionId: string) =>
    getJson<Weather>(`/v1/editions/${encodeURIComponent(editionId)}/weather`, { next: { revalidate: 1800 } }),
  goUrl: (editionId: string, raceId?: string) =>
    `${publicBase()}/v1/editions/${encodeURIComponent(editionId)}/go${raceId ? `?race=${encodeURIComponent(raceId)}` : ""}`,
  calendarUrl: (editionId: string) => `${publicBase()}/v1/editions/${encodeURIComponent(editionId)}/calendar.ics`,
};

/** SearchFilters (from the NL parser) → URL params understood by GET /v1/search and the /search page. */
export function filtersToParams(f: SearchFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.sport.length) p.set("sport", f.sport.join(","));
  if (f.discipline.length) p.set("discipline", f.discipline.join(","));
  if (f.country.length) p.set("country", f.country.join(","));
  if (f.region) p.set("region", f.region);
  if (f.near_lat != null && f.near_lon != null) {
    p.set("near", `${f.near_lat},${f.near_lon}`);
    if (f.radius_km) p.set("radius_km", String(f.radius_km));
  }
  if (f.date_from) p.set("date_from", f.date_from);
  if (f.date_to) p.set("date_to", f.date_to);
  if (f.reg_state.length) p.set("reg_state", f.reg_state.join(","));
  if (f.price_max != null) p.set("price_max", String(f.price_max));
  if (f.relay != null) p.set("relay", String(f.relay));
  for (const a of f.attributes) {
    if (a.op === "lte") p.append("attr", `${a.key}<=${a.value}`);
    else if (a.op === "gte") p.append("attr", `${a.key}>=${a.value}`);
    else p.append("attr", `${a.key}:${Array.isArray(a.value) ? a.value.join(",") : String(a.value)}`);
  }
  if (f.sort && f.sort !== "relevance") p.set("sort", f.sort);
  return p;
}
