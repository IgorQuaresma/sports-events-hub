import Link from "next/link";
import Icon from "@/components/Icon";
import RaceCard from "@/components/RaceCard";
import SearchBox from "@/components/SearchBox";
import { api, type SearchResponse } from "@/lib/api";
import { COUNTRIES, SPORTS } from "@/lib/format";
import { loadDisciplineNames } from "@/lib/taxonomy";

export const dynamic = "force-dynamic";

async function section(params: Record<string, string>): Promise<SearchResponse | null> {
  try {
    return await api.search(new URLSearchParams(params));
  } catch {
    return null;
  }
}

function SectionHeader({ id, title, href, cta }: { id: string; title: string; href: string; cta: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <h2 id={id} className="text-xl font-semibold">{title}</h2>
      <Link href={href} className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
        {cta} <Icon name="chevronRight" className="h-4 w-4" />
      </Link>
    </div>
  );
}

export default async function Home() {
  const [open, soon, names] = await Promise.all([
    section({ reg_state: "open", sort: "date", limit: "4" }),
    section({ reg_state: "not_open", sort: "date", limit: "4" }),
    loadDisciplineNames(),
  ]);
  const apiDown = open === null && soon === null;
  const sportCounts = open?.facets.sport_slug ?? {};

  return (
    <div className="space-y-12">
      <section className="-mx-4 overflow-hidden bg-gradient-to-br from-brand-800 via-brand-700 to-brand-600 px-4 py-10 text-white sm:mx-0 sm:rounded-2xl sm:px-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-3xl font-bold leading-tight sm:text-5xl">Find your next race.</h1>
          <p className="mt-3 text-base text-brand-50 sm:text-lg">
            Triathlons, runs, trail races, cycling, open water, OCR and HYROX — with registration status, prices
            and a direct link to the official sign-up. Just describe what you&apos;re looking for.
          </p>
        </div>
        <div className="mt-6 rounded-xl bg-white p-3 text-slate-900 shadow-lift sm:p-4">
          <SearchBox large />
        </div>
      </section>

      <section aria-labelledby="sports-title">
        <h2 id="sports-title" className="mb-3 text-xl font-semibold">Browse by sport</h2>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {SPORTS.map((s) => (
            <li key={s.slug}>
              <Link
                href={`/search?sport=${s.slug}&sort=date`}
                className="card flex items-center gap-3 p-3 transition hover:border-brand-300 hover:shadow-lift sm:p-4"
              >
                <span className="text-2xl" aria-hidden>{s.emoji}</span>
                <span className="font-medium text-slate-900">{s.label}</span>
                {sportCounts[s.slug] ? (
                  <span className="ml-auto text-xs text-slate-500" title="Races with open registration">
                    {sportCounts[s.slug]} open
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {apiDown && (
        <div role="alert" className="card flex items-start gap-3 border-amber-300 bg-amber-50 text-amber-900">
          <Icon name="alert" className="mt-0.5 h-5 w-5" />
          <div>
            <p className="font-semibold">Events can&apos;t be loaded right now.</p>
            <p className="text-sm">The event service is unreachable. Please try again in a moment.</p>
          </div>
        </div>
      )}

      {open && (
        <section aria-labelledby="open-title">
          <SectionHeader id="open-title" title="Registration open now" href="/search?reg_state=open&sort=date" cta={`All ${open.total}`} />
          <div className="grid gap-3">
            {open.results.map((h) => <RaceCard key={h.race_id} hit={h} disciplineNames={names} />)}
            {open.results.length === 0 && (
              <p className="card text-slate-600">No races with open registration yet. Data is refreshed regularly.</p>
            )}
          </div>
        </section>
      )}

      {soon && soon.results.length > 0 && (
        <section aria-labelledby="soon-title">
          <SectionHeader id="soon-title" title="Registration opens soon" href="/search?reg_state=not_open&sort=date" cta={`All ${soon.total}`} />
          <div className="grid gap-3">
            {soon.results.map((h) => <RaceCard key={h.race_id} hit={h} disciplineNames={names} />)}
          </div>
        </section>
      )}

      <section aria-labelledby="country-title">
        <h2 id="country-title" className="mb-3 text-xl font-semibold">Browse by country</h2>
        <ul className="grid gap-3 sm:grid-cols-3">
          {["DE", "AT", "CH"].map((c) => (
            <li key={c}>
              <Link href={`/search?country=${c}&sort=date`} className="card flex items-center gap-3 transition hover:border-brand-300 hover:shadow-lift">
                <span className="text-3xl" aria-hidden>{COUNTRIES[c].flag}</span>
                <span className="font-medium">{COUNTRIES[c].label}</span>
                <Icon name="chevronRight" className="ml-auto h-4 w-4 text-slate-400" />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="how-title" className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
        <h2 id="how-title" className="text-xl font-semibold">How it works</h2>
        <ol className="mt-4 grid gap-6 sm:grid-cols-3">
          {[
            ["search", "Describe your race", "Type it like you'd say it — “flat half marathon near Munich in autumn”. We turn it into filters you can adjust."],
            ["check", "Compare the facts", "Distances, course conditions, prices and live registration status from federations, open APIs and organizers."],
            ["external", "Register at the source", "One click takes you to the organizer's official sign-up. We never handle your registration or payment."],
          ].map(([icon, title, text], i) => (
            <li key={title} className="flex gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700" aria-hidden>
                <Icon name={icon as "search"} className="h-4 w-4" />
              </span>
              <div>
                <p className="font-semibold"><span className="sr-only">Step {i + 1}: </span>{title}</p>
                <p className="mt-1 text-sm text-slate-600">{text}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-sm text-slate-600">
          Data from World Triathlon, RunSignup, Ticketmaster, Wikidata and organizer websites.{" "}
          <Link href="/sources" className="font-medium text-brand-700 underline">See all sources</Link>
        </p>
      </section>
    </div>
  );
}
