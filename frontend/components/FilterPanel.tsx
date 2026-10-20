"use client";

import { useId, useState } from "react";
import {
  COUNTRIES, REG_STATE, SPORTS, countryLabel, disciplineLabel, sourceLabel, sportLabel,
} from "@/lib/format";
import { datePresets, isoDay, listOf } from "@/lib/params";
import Icon from "./Icon";

export type Mutate = (p: URLSearchParams) => void;

type Props = {
  params: URLSearchParams;
  facets: Record<string, Record<string, number>> | undefined;
  disciplineNames: Record<string, string>;
  update: (mutate: Mutate) => void;
};

const REG_ORDER = ["open", "not_open", "waitlist", "sold_out", "closed", "unknown"];
const RADII = [25, 50, 100, 200];
const PRICES = [50, 100, 200, 400];

function toggleIn(key: string, value: string): Mutate {
  return (p) => {
    const cur = listOf(p, key);
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    if (next.length) p.set(key, next.join(","));
    else p.delete(key);
  };
}

function Section({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group border-b border-slate-200 py-3 last:border-0">
      <summary className="flex cursor-pointer list-none items-center justify-between rounded text-sm font-semibold text-slate-900 [&::-webkit-details-marker]:hidden">
        {title}
        <Icon name="chevronDown" className="h-4 w-4 text-slate-500 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

function CheckList({
  name, options, selected, onToggle,
}: {
  name: string;
  options: { value: string; label: React.ReactNode; count?: number }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? options : options.slice(0, 6);
  return (
    <fieldset>
      <legend className="sr-only">{name}</legend>
      <ul className="space-y-0.5">
        {visible.map((o) => {
          const checked = selected.includes(o.value);
          const disabled = !checked && o.count === 0;
          return (
            <li key={o.value}>
              <label
                className={`flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-slate-100 ${
                  disabled ? "cursor-not-allowed opacity-50" : ""
                } ${checked ? "font-medium text-brand-800" : "text-slate-700"}`}
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 accent-brand-600"
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onToggle(o.value)}
                />
                <span className="flex-1">{o.label}</span>
                {o.count != null && <span className="text-xs tabular-nums text-slate-500">{o.count}</span>}
              </label>
            </li>
          );
        })}
      </ul>
      {options.length > 6 && (
        <button type="button" className="mt-1 px-2 text-sm font-medium text-brand-700 hover:underline" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer" : `Show all ${options.length}`}
        </button>
      )}
    </fieldset>
  );
}

/** Options = values with counts from the facets, plus selected values that currently have no hits. */
function facetOptions(
  facet: Record<string, number> | undefined, selected: string[], order?: string[],
): { value: string; count: number }[] {
  const counts = { ...(facet ?? {}) };
  for (const s of selected) counts[s] ??= 0;
  const entries = Object.entries(counts).map(([value, count]) => ({ value, count }));
  if (order) entries.sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
  return entries;
}

export default function FilterPanel({ params, facets, disciplineNames, update }: Props) {
  // rendered twice (sidebar + mobile dialog): ids and radio group names must be unique per instance
  const uid = useId();
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  const sports = listOf(params, "sport");
  const disciplines = listOf(params, "discipline");
  const countries = listOf(params, "country");
  const regStates = listOf(params, "reg_state");
  const sources = listOf(params, "source");
  const presets = datePresets();
  const dateTo = params.get("date_to");
  const dateFrom = params.get("date_from");
  const activePreset = !dateFrom ? (presets.find((p) => p.to === dateTo)?.key ?? (dateTo ? "custom" : "any")) : "custom";
  const near = params.get("near");
  const hideDemo = params.get("include_demo") === "false";

  function locateMe() {
    if (!("geolocation" in navigator)) {
      setGeoError("Your browser does not support location.");
      return;
    }
    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        // ~1 km precision is plenty for radius search and avoids sharing an exact position
        const lat = pos.coords.latitude.toFixed(2);
        const lon = pos.coords.longitude.toFixed(2);
        update((p) => {
          p.set("near", `${lat},${lon}`);
          if (!p.get("radius_km")) p.set("radius_km", "100");
          p.set("sort", "distance");
        });
      },
      () => {
        setLocating(false);
        setGeoError("Location permission was denied. You can still filter by country.");
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 600_000 },
    );
  }

  const sportOptions = facetOptions(facets?.sport_slug, sports, SPORTS.map((s) => s.slug)).map((o) => ({
    ...o, label: <>{SPORTS.find((s) => s.slug === o.value)?.emoji ?? "🏅"} {sportLabel(o.value)}</>,
  }));
  const disciplineOptions = facetOptions(facets?.discipline_slug, disciplines).map((o) => ({
    ...o, label: disciplineLabel(o.value, disciplineNames),
  }));
  const regOptions = facetOptions(facets?.reg_state, regStates, REG_ORDER).map((o) => ({
    ...o, label: REG_STATE[o.value]?.label ?? o.value,
  }));
  const countryOptions = facetOptions(facets?.country, countries).map((o) => ({
    ...o, label: <>{COUNTRIES[o.value]?.flag ?? "🏳️"} {countryLabel(o.value)}</>,
  }));
  const sourceOptions = facetOptions(facets?.source, sources).map((o) => ({ ...o, label: sourceLabel(o.value) }));

  return (
    <div className="text-sm">
      <Section title="Sport">
        <CheckList name="Sport" options={sportOptions} selected={sports} onToggle={(v) => update(toggleIn("sport", v))} />
      </Section>

      {disciplineOptions.length > 0 && (sports.length > 0 || disciplines.length > 0) && (
        <Section title="Distance / format">
          <CheckList name="Distance or format" options={disciplineOptions} selected={disciplines} onToggle={(v) => update(toggleIn("discipline", v))} />
        </Section>
      )}

      <Section title="When">
        <fieldset className="space-y-0.5">
          <legend className="sr-only">Date range</legend>
          {presets.map((p) => (
            <label key={p.key} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-slate-100">
              <input
                type="radio"
                name={`${uid}-when`}
                className="h-4 w-4 accent-brand-600"
                checked={activePreset === p.key}
                onChange={() => update((q) => { q.delete("date_from"); if (p.to) q.set("date_to", p.to); else q.delete("date_to"); })}
              />
              {p.label}
            </label>
          ))}
        </fieldset>
        <div className="mt-2 grid grid-cols-2 gap-2 px-2">
          <div>
            <label className="label" htmlFor={`${uid}-date_from`}>From</label>
            <input
              id={`${uid}-date_from`} type="date" className="input px-2" min={isoDay(new Date())}
              value={dateFrom ?? ""}
              onChange={(e) => update((q) => { if (e.target.value) q.set("date_from", e.target.value); else q.delete("date_from"); })}
            />
          </div>
          <div>
            <label className="label" htmlFor={`${uid}-date_to`}>To</label>
            <input
              id={`${uid}-date_to`} type="date" className="input px-2" min={dateFrom ?? isoDay(new Date())}
              value={dateTo ?? ""}
              onChange={(e) => update((q) => { if (e.target.value) q.set("date_to", e.target.value); else q.delete("date_to"); })}
            />
          </div>
        </div>
      </Section>

      <Section title="Registration">
        <CheckList name="Registration status" options={regOptions} selected={regStates} onToggle={(v) => update(toggleIn("reg_state", v))} />
      </Section>

      <Section title="Where">
        <CheckList name="Country" options={countryOptions} selected={countries} onToggle={(v) => update(toggleIn("country", v))} />
        <div className="mt-3 space-y-2 px-2">
          {near ? (
            <div className="flex items-center justify-between gap-2 rounded-lg bg-brand-50 px-3 py-2 text-brand-900">
              <span className="inline-flex items-center gap-1.5"><Icon name="locate" /> Near you</span>
              <button type="button" className="text-sm font-medium underline" onClick={() => update((p) => { p.delete("near"); p.delete("radius_km"); if (p.get("sort") === "distance") p.delete("sort"); })}>
                Remove
              </button>
            </div>
          ) : (
            <button type="button" className="btn-secondary w-full" onClick={locateMe} disabled={locating}>
              <Icon name="locate" /> {locating ? "Locating…" : "Use my location"}
            </button>
          )}
          {near && (
            <div>
              <label className="label" htmlFor={`${uid}-radius`}>Within</label>
              <select
                id={`${uid}-radius`} className="input"
                value={params.get("radius_km") ?? "100"}
                onChange={(e) => update((p) => p.set("radius_km", e.target.value))}
              >
                {RADII.map((r) => <option key={r} value={r}>{r} km</option>)}
              </select>
            </div>
          )}
          {geoError && <p role="alert" className="text-xs text-rose-700">{geoError}</p>}
        </div>
      </Section>

      <Section title="Price" defaultOpen={!!params.get("price_max")}>
        <div className="px-2">
          <label className="label" htmlFor={`${uid}-price_max`}>Entry fee up to</label>
          <select
            id={`${uid}-price_max`} className="input"
            value={params.get("price_max") ?? ""}
            onChange={(e) => update((p) => { if (e.target.value) p.set("price_max", e.target.value); else p.delete("price_max"); })}
          >
            <option value="">Any price</option>
            {PRICES.map((v) => <option key={v} value={v}>€{v}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">Events without a known price are hidden when a limit is set.</p>
        </div>
      </Section>

      <Section title="Data source" defaultOpen={sources.length > 0 || hideDemo}>
        <CheckList name="Data source" options={sourceOptions} selected={sources} onToggle={(v) => update(toggleIn("source", v))} />
        <label className="mt-2 flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-slate-100">
          <input
            type="checkbox" className="h-4 w-4 accent-brand-600" checked={hideDemo}
            onChange={() => update((p) => { if (hideDemo) p.delete("include_demo"); else p.set("include_demo", "false"); })}
          />
          Hide demo data
        </label>
      </Section>
    </div>
  );
}
