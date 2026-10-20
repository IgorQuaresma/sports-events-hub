"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FilterPanel, { type Mutate } from "@/components/FilterPanel";
import { listOf } from "@/lib/params";
import Icon from "@/components/Icon";
import RaceCard, { RaceCardSkeleton } from "@/components/RaceCard";
import SearchBox from "@/components/SearchBox";
import { ApiError, api, type SearchResponse } from "@/lib/api";
import {
  attributeChips, countryLabel, disciplineLabel, formatDate, regStateLabel, sourceLabel, sportLabel,
} from "@/lib/format";

const PAGE = 20;
const FILTER_KEYS = [
  "q", "sport", "discipline", "country", "region", "near", "date_from", "date_to", "reg_state", "price_max",
  "relay", "attr", "source", "include_demo",
];

type Chip = { key: string; label: string; remove: Mutate };

/** Human-readable, individually removable chips for every active URL filter. */
function describe(params: URLSearchParams, disciplineNames: Record<string, string>): Chip[] {
  const chips: Chip[] = [];
  const list = (key: string, fmt: (v: string) => string) => {
    for (const v of listOf(params, key)) {
      chips.push({
        key: `${key}:${v}`,
        label: fmt(v),
        remove: (p) => {
          const rest = listOf(p, key).filter((x) => x !== v);
          if (rest.length) p.set(key, rest.join(","));
          else p.delete(key);
        },
      });
    }
  };
  if (params.get("q")) chips.push({ key: "q", label: `“${params.get("q")}”`, remove: (p) => p.delete("q") });
  list("sport", sportLabel);
  list("discipline", (v) => disciplineLabel(v, disciplineNames));
  list("country", countryLabel);
  list("reg_state", regStateLabel);
  list("source", sourceLabel);
  if (params.get("region")) chips.push({ key: "region", label: params.get("region")!, remove: (p) => p.delete("region") });
  if (params.get("near"))
    chips.push({
      key: "near",
      label: `Within ${params.get("radius_km") || 100} km`,
      remove: (p) => { p.delete("near"); p.delete("radius_km"); if (p.get("sort") === "distance") p.delete("sort"); },
    });
  const from = params.get("date_from");
  const to = params.get("date_to");
  if (from || to)
    chips.push({
      key: "date",
      label: from && to ? `${formatDate(from)} – ${formatDate(to)}` : from ? `From ${formatDate(from)}` : `Until ${formatDate(to!)}`,
      remove: (p) => { p.delete("date_from"); p.delete("date_to"); },
    });
  if (params.get("price_max")) chips.push({ key: "price", label: `Up to €${params.get("price_max")}`, remove: (p) => p.delete("price_max") });
  if (params.get("relay") === "true") chips.push({ key: "relay", label: "Relay", remove: (p) => p.delete("relay") });
  if (params.get("include_demo") === "false") chips.push({ key: "demo", label: "No demo data", remove: (p) => p.delete("include_demo") });
  for (const a of params.getAll("attr")) {
    const [k, v] = a.includes(":") ? a.split(":", 2) : [a, ""];
    const label = v ? (attributeChips({ [k]: v.split(",")[0] === "true" ? true : v.split(",")[0] })[0] ?? a) : a.replace(/_/g, " ");
    chips.push({
      key: `attr:${a}`,
      label: v.includes(",") ? `${label} (or similar)` : label,
      remove: (p) => {
        const rest = p.getAll("attr").filter((x) => x !== a);
        p.delete("attr");
        rest.forEach((x) => p.append("attr", x));
      },
    });
  }
  return chips;
}

export default function SearchClient({ disciplineNames }: { disciplineNames: Record<string, string> }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const resultsRef = useRef<HTMLHeadingElement>(null);

  const apiParams = useMemo(() => {
    const p = new URLSearchParams(searchParams.toString());
    p.delete("nl");
    p.set("limit", String(PAGE));
    return p;
  }, [searchParams]);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    api
      .search(apiParams, ctrl.signal)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => {
        if (ctrl.signal.aborted) return; // superseded by a newer request
        setError(
          e instanceof ApiError && e.status === 422
            ? `Some filters are invalid: ${e.message}`
            : "We couldn't load events right now. Check your connection and try again.",
        );
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [apiParams, attempt]);

  const update = useCallback(
    (mutate: Mutate) => {
      const p = new URLSearchParams(searchParams.toString());
      mutate(p);
      p.delete("offset");
      router.push(`/search?${p.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const goToPage = (offset: number) => {
    const p = new URLSearchParams(searchParams.toString());
    if (offset > 0) p.set("offset", String(offset));
    else p.delete("offset");
    router.push(`/search?${p.toString()}`, { scroll: false });
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    resultsRef.current?.focus({ preventScroll: true });
  };

  const chips = describe(searchParams, disciplineNames);
  const offset = Number(searchParams.get("offset") || 0);
  const nl = searchParams.get("nl") || "";
  const activeFilterCount = FILTER_KEYS.filter((k) => searchParams.has(k)).length;
  const sort = searchParams.get("sort") || "relevance";
  const pages = data ? Math.ceil(data.total / PAGE) : 0;
  const page = Math.floor(offset / PAGE) + 1;
  const firstLoad = loading && !data;

  const panel = (
    <FilterPanel params={searchParams} facets={data?.facets} disciplineNames={disciplineNames} update={update} />
  );

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <h1 className="text-2xl font-bold sm:text-3xl">Find a race</h1>
        <SearchBox initial={nl || searchParams.get("q") || ""} keepParams={["include_demo"]} />
        {nl && (
          <p className="flex items-center gap-1.5 text-sm text-slate-600">
            <Icon name="sparkles" className="h-4 w-4 text-brand-600" />
            We turned your search into the filters below — remove any that don&apos;t fit.
          </p>
        )}
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {chips.map((c) => (
            <button key={c.key} type="button" className="chip chip-active" onClick={() => update(c.remove)}>
              {c.label}
              <Icon name="x" className="h-3.5 w-3.5" />
              <span className="sr-only">Remove filter</span>
            </button>
          ))}
          <button type="button" className="px-2 text-sm font-medium text-slate-600 underline hover:text-slate-900" onClick={() => router.push("/search")}>
            Clear all
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block" aria-label="Filters">
          <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-xl border border-slate-200 bg-white px-4 py-1 shadow-card">
            {panel}
          </div>
        </aside>

        <section aria-labelledby="results-heading" className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 id="results-heading" ref={resultsRef} tabIndex={-1} className="text-sm text-slate-700 focus:outline-none" aria-live="polite">
              {firstLoad ? "Searching…" : data ? (
                <>
                  <strong className="text-slate-900">{data.total.toLocaleString("en-GB")}</strong> race{data.total === 1 ? "" : "s"}
                  {pages > 1 && <span className="text-slate-500"> · page {page} of {pages}</span>}
                </>
              ) : ""}
            </h2>
            <div className="flex items-center gap-2">
              <button type="button" className="btn-secondary lg:hidden" onClick={() => dialogRef.current?.showModal()}>
                <Icon name="filter" /> Filters
                {activeFilterCount > 0 && (
                  <span className="rounded-full bg-brand-600 px-1.5 text-xs text-white">{activeFilterCount}</span>
                )}
              </button>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <span className="hidden sm:inline">Sort by</span>
                <select
                  value={sort}
                  aria-label="Sort results"
                  onChange={(e) => update((p) => { if (e.target.value === "relevance") p.delete("sort"); else p.set("sort", e.target.value); })}
                  className="input w-auto py-2"
                >
                  <option value="relevance">Best match</option>
                  <option value="date">Date (soonest)</option>
                  <option value="price">Price (lowest)</option>
                  {searchParams.get("near") && <option value="distance">Distance</option>}
                </select>
              </label>
            </div>
          </div>

          {error && (
            <div role="alert" className="card mb-3 flex flex-wrap items-center justify-between gap-3 border-rose-200 bg-rose-50 text-sm text-rose-900">
              <span className="inline-flex items-center gap-2"><Icon name="alert" /> {error}</span>
              <button type="button" className="btn-secondary" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
            </div>
          )}

          <div className={`grid gap-3 transition-opacity ${loading && data ? "opacity-60" : ""}`} aria-busy={loading}>
            {firstLoad && Array.from({ length: 5 }, (_, i) => <RaceCardSkeleton key={i} />)}
            {data?.results.map((h) => <RaceCard key={h.race_id} hit={h} disciplineNames={disciplineNames} />)}
          </div>

          {data && data.results.length === 0 && !loading && !error && (
            <div className="card py-10 text-center">
              <Icon name="search" className="mx-auto h-8 w-8 text-slate-400" />
              <h3 className="mt-3 text-lg font-semibold">No races match these filters</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
                Try removing a filter, widening the date range or the radius, or searching across all sports.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {chips.length > 0 && (
                  <button type="button" className="btn-secondary" onClick={() => update(chips[chips.length - 1].remove)}>
                    Remove “{chips[chips.length - 1].label}”
                  </button>
                )}
                <Link href="/search?sort=date" className="btn-primary">Show all upcoming events</Link>
              </div>
            </div>
          )}

          {data && pages > 1 && (
            <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-3">
              <button type="button" className="btn-secondary" disabled={offset === 0} onClick={() => goToPage(Math.max(0, offset - PAGE))}>
                <Icon name="chevronLeft" /> Previous
              </button>
              <span className="text-sm text-slate-600">
                {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
              </span>
              <button type="button" className="btn-secondary" disabled={offset + PAGE >= data.total} onClick={() => goToPage(offset + PAGE)}>
                Next <Icon name="chevronRight" />
              </button>
            </nav>
          )}
        </section>
      </div>

      {/* Mobile filters: native <dialog> gives focus trapping and Escape-to-close for free */}
      <dialog
        ref={dialogRef}
        aria-labelledby="filters-title"
        className="m-0 ml-auto h-full max-h-none w-full max-w-sm bg-white p-0 shadow-xl backdrop:bg-slate-900/40"
        onClick={(e) => { if (e.target === dialogRef.current) dialogRef.current?.close(); }}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 id="filters-title" className="text-base font-semibold">Filters</h2>
            <button type="button" className="btn-ghost px-2" onClick={() => dialogRef.current?.close()}>
              <Icon name="x" className="h-5 w-5" /><span className="sr-only">Close filters</span>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-4">{panel}</div>
          <div className="flex gap-2 border-t border-slate-200 p-4">
            <button type="button" className="btn-secondary flex-1" onClick={() => router.push("/search")}>Clear all</button>
            <button type="button" className="btn-primary flex-1" onClick={() => dialogRef.current?.close()}>
              {loading ? "Updating…" : `Show ${data?.total ?? 0} results`}
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
