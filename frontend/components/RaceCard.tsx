import Link from "next/link";
import { api, type SearchHit } from "@/lib/api";
import {
  attributeChips, countryLabel, dateParts, disciplineLabel, formatDate, formatDistances, formatPrice, isDemo,
  relativeDay, sportLabel, timeAgo,
} from "@/lib/format";
import Icon from "./Icon";
import RegistrationBadge from "./RegistrationBadge";

export default function RaceCard({
  hit, disciplineNames,
}: { hit: SearchHit; disciplineNames?: Record<string, string> }) {
  const chips = attributeChips(hit.attributes).slice(0, 4);
  const d = dateParts(hit.start_date);
  const distances = formatDistances(hit.distances);
  const demo = isDemo(hit.source_keys);
  const place = [hit.city, hit.region && hit.region !== hit.city ? hit.region : null].filter(Boolean).join(", ");
  const showRaceName = hit.race_name !== hit.event_name;

  return (
    <article className="card group relative flex gap-4 transition-shadow hover:shadow-lift">
      <div
        className="flex h-16 w-14 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-50 text-brand-800"
        aria-hidden
      >
        <span className="text-[11px] font-semibold uppercase">{d.month}</span>
        <span className="text-xl font-bold leading-none">{d.day}</span>
        <span className="text-[11px]">{d.weekday}</span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
            <span className="font-semibold uppercase tracking-wide text-brand-700">{sportLabel(hit.sport_slug)}</span>
            <span aria-hidden>·</span>
            <span>{disciplineLabel(hit.discipline_slug, disciplineNames, hit.sport_slug)}</span>
            {hit.relay && <span className="badge bg-slate-100 text-slate-700">Relay</span>}
            {demo && <span className="badge bg-amber-100 text-amber-900">Demo data</span>}
          </div>

          <h3 className="mt-1 text-lg font-semibold leading-snug text-slate-900">
            {/* stretched link: the whole card is clickable; the Register button stays its own target */}
            <Link
              href={`/events/${hit.event_slug}`}
              className="after:absolute after:inset-0 after:rounded-xl group-hover:text-brand-700"
            >
              {hit.event_name}
            </Link>
          </h3>
          {(showRaceName || distances) && (
            <p className="text-sm text-slate-700">
              {showRaceName && hit.race_name}
              {showRaceName && distances && " — "}
              {distances}
            </p>
          )}

          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
            <span className="inline-flex items-center gap-1">
              <Icon name="calendar" className="h-3.5 w-3.5 text-slate-400" />
              <time dateTime={hit.start_date}>{formatDate(hit.start_date)}</time>
              <span className="text-slate-500">({relativeDay(hit.start_date)})</span>
            </span>
            {(place || hit.country) && (
              <span className="inline-flex items-center gap-1">
                <Icon name="pin" className="h-3.5 w-3.5 text-slate-400" />
                {place || "Location TBA"}
                {hit.country && <span className="text-slate-500">· {countryLabel(hit.country)}</span>}
              </span>
            )}
            {hit.distance_km != null && (
              <span className="font-medium text-slate-700">{Math.round(hit.distance_km)} km away</span>
            )}
          </p>

          {chips.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Race conditions">
              {chips.map((c) => (
                <li key={c} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{c}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="relative z-10 flex shrink-0 flex-row flex-wrap items-center gap-2 sm:flex-col sm:items-end">
          <RegistrationBadge state={hit.reg_state} checkedAt={hit.reg_checked_at} />
          {hit.price_from && (
            <span className="text-sm text-slate-700">
              from <strong className="text-slate-900">{formatPrice(hit.price_from, hit.currency)}</strong>
            </span>
          )}
          {hit.reg_closes_at && hit.reg_state === "open" && (
            <span className="text-xs text-slate-600">closes {formatDate(hit.reg_closes_at)}</span>
          )}
          {hit.registration_url && hit.reg_state !== "closed" && hit.reg_state !== "sold_out" && (
            <a
              href={api.goUrl(hit.edition_id, hit.race_id)}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="btn-primary px-3 py-1.5"
            >
              Register <Icon name="external" className="h-3.5 w-3.5" />
              <span className="sr-only">for {hit.event_name} on the official site (opens in a new tab)</span>
            </a>
          )}
          {hit.reg_checked_at && (
            <span className="text-[11px] text-slate-500">status checked {timeAgo(hit.reg_checked_at)}</span>
          )}
        </div>
      </div>
    </article>
  );
}

export function RaceCardSkeleton() {
  return (
    <div className="card flex gap-4" aria-hidden>
      <div className="skeleton h-16 w-14 rounded-lg" />
      <div className="flex-1 space-y-2">
        <div className="skeleton h-3 w-32" />
        <div className="skeleton h-5 w-2/3" />
        <div className="skeleton h-3 w-1/2" />
        <div className="skeleton h-3 w-1/3" />
      </div>
      <div className="hidden w-28 space-y-2 sm:block">
        <div className="skeleton ml-auto h-5 w-24" />
        <div className="skeleton ml-auto h-8 w-24" />
      </div>
    </div>
  );
}
