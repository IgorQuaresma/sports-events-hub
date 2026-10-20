import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Icon from "@/components/Icon";
import RegistrationBadge from "@/components/RegistrationBadge";
import ShareButton from "@/components/ShareButton";
import WeatherCard from "@/components/WeatherCard";
import { ApiError, api, type EventDetail, type Race, type Weather } from "@/lib/api";
import {
  LOCALE, attributeRows, countryLabel, disciplineLabel, formatDate, formatDateRange, formatDistances, formatPrice,
  relativeDay, sourceLabel, sportLabel, timeAgo,
} from "@/lib/format";
import { loadDisciplineNames } from "@/lib/taxonomy";

type Props = { params: Promise<{ slug: string }> };

const STATE_RANK = ["open", "waitlist", "not_open", "sold_out", "closed", "unknown"];
// Race times are venue-local; all our current countries share Central European Time.
const VENUE_TZ: Record<string, string> = { DE: "Europe/Berlin", AT: "Europe/Vienna", CH: "Europe/Zurich" };

async function load(slug: string): Promise<EventDetail | null> {
  try {
    return await api.event(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

async function loadWeather(editionId: string): Promise<Weather | null> {
  try {
    return await api.weather(editionId);
  } catch {
    return null; // weather is a nice-to-have; never break the page for it
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const ev = await load(slug);
  if (!ev) return { title: "Event not found" };
  const ne = ev.next_edition;
  const where = ne?.venue ? [ne.venue.city, countryLabel(ne.venue.country)].filter(Boolean).join(", ") : "";
  return {
    title: ne ? `${ev.name} ${ne.year}` : ev.name,
    description: ne
      ? `${formatDateRange(ne.start_date, ne.end_date)}${where ? ` · ${where}` : ""} — races, distances, registration status and prices.`
      : undefined,
    robots: ev.is_demo ? { index: false } : undefined,
  };
}

function bestState(races: Race[]): string {
  const states = races.map((r) => r.registration?.state ?? "unknown");
  return STATE_RANK.find((s) => states.includes(s)) ?? "unknown";
}

function mapUrl(v: NonNullable<EventDetail["next_edition"]>["venue"]): string | null {
  if (!v) return null;
  if (v.lat != null && v.lon != null) {
    return `https://www.openstreetmap.org/?mlat=${v.lat}&mlon=${v.lon}#map=13/${v.lat}/${v.lon}`;
  }
  const q = [v.name, v.street, v.postal_code, v.city, v.country].filter(Boolean).join(", ");
  return q ? `https://www.openstreetmap.org/search?query=${encodeURIComponent(q)}` : null;
}

/** schema.org markup for search engines. `<` is escaped so data can never close the script tag. */
function jsonLd(ev: EventDetail): string | null {
  const ne = ev.next_edition;
  if (!ne || ev.is_demo) return null;
  const data = {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    name: `${ev.name} ${ne.year}`,
    startDate: ne.start_date,
    endDate: ne.end_date ?? ne.start_date,
    eventStatus: ne.status === "cancelled" ? "https://schema.org/EventCancelled" : "https://schema.org/EventScheduled",
    sport: sportLabel(ev.sport_slug),
    location: ne.venue
      ? {
          "@type": "Place",
          name: ne.venue.name ?? ne.venue.city ?? undefined,
          address: { "@type": "PostalAddress", addressLocality: ne.venue.city ?? undefined, addressCountry: ne.venue.country },
          ...(ne.venue.lat != null ? { geo: { "@type": "GeoCoordinates", latitude: ne.venue.lat, longitude: ne.venue.lon } } : {}),
        }
      : undefined,
    url: ev.website ?? undefined,
    organizer: ev.organizer_name ? { "@type": "Organization", name: ev.organizer_name } : undefined,
  };
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

function RaceDetails({ race, editionId, fallbackUrl, sport, tz, names }: {
  race: Race; editionId: string; fallbackUrl: string | null; sport: string; tz?: string; names: Record<string, string>;
}) {
  const reg = race.registration;
  const distances = formatDistances(race.distances);
  const rows = attributeRows(race.attributes);
  const canRegister = (reg?.url || fallbackUrl) && reg?.state !== "closed" && reg?.state !== "sold_out";
  return (
    <article className="card" aria-labelledby={`race-${race.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={`race-${race.id}`} className="text-base font-semibold text-slate-900">{race.name}</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            {disciplineLabel(race.discipline_slug, names, sport)}
            {race.relay && " · relay"}
            {race.team && !race.relay && " · team"}
          </p>
        </div>
        {reg && <RegistrationBadge state={reg.state} checkedAt={reg.state_checked_at} />}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        {distances && (
          <div className="col-span-2 sm:col-span-3">
            <dt className="label">Distances</dt>
            <dd className="font-medium text-slate-900">{distances}</dd>
          </div>
        )}
        {race.start_time && (
          <div>
            <dt className="label">Start</dt>
            <dd>
              {new Date(race.start_time).toLocaleString(LOCALE, {
                weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz,
              })}
            </dd>
          </div>
        )}
        {race.participant_limit && (
          <div>
            <dt className="label">Field limit</dt>
            <dd>
              {race.participant_limit.toLocaleString(LOCALE)}
              {race.participants_registered != null && (
                <span className="text-slate-500"> ({race.participants_registered.toLocaleString(LOCALE)} registered)</span>
              )}
            </dd>
          </div>
        )}
        {rows.map((r) => (
          <div key={r.label}>
            <dt className="label">{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>

      {reg && (reg.price_tiers.length > 0 || reg.opens_at || reg.closes_at || canRegister) && (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3 text-sm">
          {reg.opens_at && reg.state === "not_open" && <span>Opens <strong>{formatDate(reg.opens_at)}</strong></span>}
          {reg.closes_at && <span className="text-slate-600">Closes {formatDate(reg.closes_at)}</span>}
          {reg.price_tiers.length > 0 && (
            <ul className="flex flex-wrap gap-1.5" aria-label="Entry fees">
              {reg.price_tiers.map((t, i) => (
                <li key={i} className="rounded-md bg-slate-100 px-2 py-0.5">
                  {t.label ?? "Entry"}: <strong>{formatPrice(t.amount, t.currency)}</strong>
                  {t.valid_until && <span className="text-slate-500"> until {formatDate(t.valid_until)}</span>}
                </li>
              ))}
            </ul>
          )}
          {canRegister && (
            <a href={api.goUrl(editionId, race.id)} target="_blank" rel="noopener noreferrer nofollow" className="btn-primary ml-auto">
              Register <Icon name="external" className="h-3.5 w-3.5" />
              <span className="sr-only">for {race.name} (official site, new tab)</span>
            </a>
          )}
        </div>
      )}
    </article>
  );
}

export default async function EventPage({ params }: Props) {
  const { slug } = await params;
  const ev = await load(slug);
  if (!ev) notFound();
  const ne = ev.next_edition;
  const [weather, names] = await Promise.all([ne ? loadWeather(ne.id) : null, loadDisciplineNames()]);
  const overall = ne ? bestState(ne.races) : "unknown";
  const venue = ne?.venue;
  const map = mapUrl(venue ?? null);
  const tz = venue ? VENUE_TZ[venue.country] : undefined;
  const ld = jsonLd(ev);
  const isPast = ne ? (ne.end_date ?? ne.start_date) < new Date().toISOString().slice(0, 10) : false;
  const sources = [...new Set(ne?.provenance.map((p) => p.source_key) ?? [])];

  return (
    <article className="space-y-6">
      {ld && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: ld }} />}

      <nav aria-label="Breadcrumb" className="text-sm text-slate-600">
        <ol className="flex flex-wrap items-center gap-1">
          <li><Link href="/" className="hover:text-brand-700 hover:underline">Home</Link></li>
          <li aria-hidden>/</li>
          <li><Link href={`/search?sport=${ev.sport_slug}`} className="hover:text-brand-700 hover:underline">{sportLabel(ev.sport_slug)}</Link></li>
          <li aria-hidden>/</li>
          <li aria-current="page" className="truncate text-slate-900">{ev.name}</li>
        </ol>
      </nav>

      {ev.is_demo && (
        <div role="note" className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <Icon name="info" className="mt-0.5 h-4 w-4" />
          <span><strong>Demo data.</strong> This is a fictional sample event used to show how the hub works — it is not a real race.</span>
        </div>
      )}
      {ne && (ne.status === "cancelled" || ne.status === "postponed") && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-900">
          <Icon name="alert" className="mt-0.5 h-4 w-4" />
          <span>This edition has been <strong>{ne.status}</strong>. Check the organizer&apos;s website for details.</span>
        </div>
      )}

      <header className="space-y-3">
        <span className="badge bg-brand-50 text-brand-800">{sportLabel(ev.sport_slug)}</span>
        <h1 className="text-3xl font-bold leading-tight sm:text-4xl">
          {ev.name}
          {ne && !ev.name.includes(String(ne.year)) && <span className="text-slate-500"> {ne.year}</span>}
        </h1>
        {ne && (
          <ul className="flex flex-wrap gap-x-5 gap-y-2 text-slate-700">
            <li className="inline-flex items-center gap-1.5">
              <Icon name="calendar" className="h-4 w-4 text-slate-500" />
              <time dateTime={ne.start_date}>{formatDateRange(ne.start_date, ne.end_date)}</time>
              <span className="text-slate-500">({relativeDay(ne.start_date)})</span>
            </li>
            {venue && (
              <li className="inline-flex items-center gap-1.5">
                <Icon name="pin" className="h-4 w-4 text-slate-500" />
                {[venue.name, venue.city, venue.region].filter(Boolean).join(", ") || "Venue TBA"}, {countryLabel(venue.country)}
                {map && (
                  <a href={map} target="_blank" rel="noopener noreferrer" className="ml-1 text-sm font-medium text-brand-700 underline">
                    Map<span className="sr-only"> (OpenStreetMap, new tab)</span>
                  </a>
                )}
              </li>
            )}
          </ul>
        )}
        {ev.organizer_name && <p className="text-sm text-slate-600">Organized by {ev.organizer_name}</p>}

        {ne && (
          <div className="flex flex-wrap gap-2 pt-1">
            {ne.registration_url && !isPast && overall !== "closed" && overall !== "sold_out" && (
              <a href={api.goUrl(ne.id)} target="_blank" rel="noopener noreferrer nofollow" className="btn-primary">
                Register on official site <Icon name="external" className="h-3.5 w-3.5" />
              </a>
            )}
            {!isPast && (
              <a href={api.calendarUrl(ne.id)} className="btn-secondary" download>
                <Icon name="calendar" /> Add to calendar
              </a>
            )}
            {(ev.website || ne.info_url) && (
              <a href={ev.website ?? ne.info_url ?? "#"} target="_blank" rel="noopener noreferrer" className="btn-secondary">
                Event website <Icon name="external" className="h-3.5 w-3.5" />
              </a>
            )}
            <ShareButton title={`${ev.name} ${ne.year}`} />
          </div>
        )}
      </header>

      {!ne && <p className="text-slate-600">No dates are known for this event yet.</p>}

      {ne && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="min-w-0 space-y-6">
            {(ne.summary || ev.description) && (
              <section aria-labelledby="about-title">
                <h2 id="about-title" className="mb-2 text-xl font-semibold">About</h2>
                <p className="max-w-prose whitespace-pre-line text-slate-800">{ne.summary ?? ev.description}</p>
              </section>
            )}

            <section aria-labelledby="races-title" className="space-y-3">
              <h2 id="races-title" className="text-xl font-semibold">
                Races <span className="text-base font-normal text-slate-500">({ne.races.length})</span>
              </h2>
              {ne.races.map((r) => (
                <RaceDetails key={r.id} race={r} editionId={ne.id} fallbackUrl={ne.registration_url} sport={ev.sport_slug} tz={tz} names={names} />
              ))}
            </section>

            {ev.editions.length > 1 && (
              <section aria-labelledby="editions-title">
                <h2 id="editions-title" className="mb-2 text-lg font-semibold">Other editions</h2>
                <ul className="flex flex-wrap gap-2 text-sm">
                  {ev.editions.map((e) => (
                    <li key={e.id} className={`chip cursor-default ${e.id === ne.id ? "chip-active" : ""}`} aria-current={e.id === ne.id ? "true" : undefined}>
                      {e.year} · {formatDate(e.start_date)}{e.status !== "scheduled" ? ` · ${e.status}` : ""}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
            <section className="card space-y-3" aria-labelledby="reg-title">
              <h2 id="reg-title" className="text-base font-semibold">Registration</h2>
              <RegistrationBadge state={overall} />
              {ne.registration_url && !isPast && overall !== "closed" && overall !== "sold_out" ? (
                <a href={api.goUrl(ne.id)} target="_blank" rel="noopener noreferrer nofollow" className="btn-primary w-full">
                  Go to official registration <Icon name="external" className="h-3.5 w-3.5" />
                </a>
              ) : (
                <p className="text-sm text-slate-600">
                  {isPast ? "This edition has already taken place." : "No registration link is known yet — check the event website."}
                </p>
              )}
              {ne.registration_platform && (
                <p className="text-xs text-slate-600">Handled by: {sourceLabel(ne.registration_platform)}</p>
              )}
              <p className="text-xs text-slate-500">
                Registration, payment and terms are handled by the organizer. We never ask for your payment details.
              </p>
            </section>

            <WeatherCard weather={weather} />

            <section className="card space-y-2 text-sm" aria-labelledby="prov-title">
              <h2 id="prov-title" className="flex items-center gap-2 text-base font-semibold">
                <Icon name="database" className="h-4 w-4 text-slate-500" /> Where this data comes from
              </h2>
              <ul className="space-y-1.5 text-slate-700">
                {ne.provenance.map((p, i) => (
                  <li key={i}>
                    <a href={p.url} className="font-medium text-brand-700 underline" target="_blank" rel="noopener noreferrer">
                      {p.source_name}
                    </a>
                    <span className="text-slate-500"> · updated {timeAgo(p.fetched_at)}</span>
                    {p.parse_confidence != null && p.parse_confidence < 0.8 && (
                      <span className="ml-1 text-amber-800">(automatically extracted — please double-check)</span>
                    )}
                  </li>
                ))}
              </ul>
              {ne.data_quality_score != null && (
                <div>
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>Data completeness</span><span>{Math.round(ne.data_quality_score * 100)}%</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-slate-100" role="presentation">
                    <div className="h-1.5 rounded-full bg-brand-500" style={{ width: `${Math.round(ne.data_quality_score * 100)}%` }} />
                  </div>
                </div>
              )}
              <p className="pt-1 text-xs text-slate-600">
                {sources.length > 0 && <><Link href="/sources" className="underline">About our sources</Link> · </>}
                <a href={`mailto:data@example.org?subject=${encodeURIComponent(`Error report: ${ev.name} ${ne.year}`)}`} className="underline">
                  Report an error
                </a>
              </p>
            </section>
          </aside>
        </div>
      )}
    </article>
  );
}
