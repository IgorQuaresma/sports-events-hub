"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { api, filtersToParams } from "@/lib/api";
import Icon from "./Icon";

const EXAMPLES = [
  "Olympic triathlon in Germany in June, wetsuit allowed",
  "Halbmarathon nähe München im Herbst unter 50 €",
  "Ultra trail Schweiz 2027",
  "HYROX Wien",
];

export default function SearchBox({
  initial = "", large = false, keepParams,
}: { initial?: string; large?: boolean; keepParams?: string[] }) {
  const router = useRouter();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(initial);
  const [busy, setBusy] = useState(false);

  async function submit(q: string) {
    const text = q.trim();
    if (!text) {
      router.push("/search");
      return;
    }
    setBusy(true);
    let params: URLSearchParams;
    try {
      // Natural language → structured filters, shown back to the user as removable chips.
      const parsed = await api.parse(text);
      params = filtersToParams(parsed.filters);
    } catch {
      // Parser unavailable or rate-limited: a plain full-text search still works.
      params = new URLSearchParams({ q: text });
    }
    params.set("nl", text);
    const current = new URLSearchParams(window.location.search);
    for (const k of keepParams ?? []) {
      const v = current.get(k);
      if (v && !params.has(k)) params.set(k, v);
    }
    router.push(`/search?${params.toString()}`);
    setBusy(false);
  }

  return (
    <div className="w-full">
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(query);
        }}
        className={`flex gap-2 ${large ? "flex-col sm:flex-row" : ""}`}
      >
        <label htmlFor={inputId} className="sr-only">
          Describe the race you are looking for
        </label>
        <div className="relative flex-1">
          <Icon
            name="search"
            className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 ${large ? "h-5 w-5" : "h-4 w-4"}`}
          />
          <input
            ref={inputRef}
            id={inputId}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={300}
            autoComplete="off"
            enterKeyHint="search"
            placeholder="e.g. olympic triathlon near Hamburg in June"
            className={`input pl-10 pr-10 shadow-sm ${large ? "py-3.5 text-base sm:text-lg" : "py-2.5"}`}
          />
          {query && !busy && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Clear search text"
            >
              <Icon name="x" />
            </button>
          )}
        </div>
        <button type="submit" disabled={busy} className={`btn-primary ${large ? "px-6 text-base" : ""}`} aria-busy={busy}>
          {busy ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
              Understanding…
            </>
          ) : (
            "Search"
          )}
        </button>
      </form>
      {large && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="chip text-xs"
              disabled={busy}
              onClick={() => {
                setQuery(ex);
                void submit(ex);
              }}
            >
              {ex}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
