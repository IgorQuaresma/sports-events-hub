import type { Metadata } from "next";
import Icon from "@/components/Icon";
import { api, type Sources } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export const metadata: Metadata = {
  title: "Data sources",
  description: "Where Sports Events Hub gets its event data, under which terms, and how fresh it is.",
};
export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  let data: Sources | null = null;
  try {
    data = await api.sources();
  } catch {
    data = null;
  }

  return (
    <div className="max-w-3xl space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold">Data sources</h1>
        <p className="text-slate-700">
          Every event shows where its data came from and when it was last checked. We prefer official and open
          sources, respect each provider&apos;s terms and robots.txt, and always send you to the organizer for
          registration.
        </p>
      </header>

      {!data && (
        <p role="alert" className="card border-amber-300 bg-amber-50 text-amber-900">
          The source list can&apos;t be loaded right now.
        </p>
      )}

      {data && (
        <section aria-labelledby="event-sources" className="space-y-3">
          <h2 id="event-sources" className="text-xl font-semibold">Event data</h2>
          <ul className="grid gap-3">
            {data.sources.map((s) => (
              <li key={s.key} className="card">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">
                      {s.homepage ? (
                        <a href={s.homepage} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-brand-700">
                          {s.name} <Icon name="external" className="h-3.5 w-3.5" />
                        </a>
                      ) : s.name}
                    </h3>
                    {s.attribution && <p className="text-sm text-slate-700">{s.attribution}</p>}
                  </div>
                  {s.is_demo ? (
                    <span className="badge bg-amber-100 text-amber-900">Demo</span>
                  ) : (
                    <span className="badge bg-slate-100 text-slate-700">{s.kind.toUpperCase()}</span>
                  )}
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                  <div><dt className="label">Editions</dt><dd>{s.editions.toLocaleString("en-GB")}</dd></div>
                  <div><dt className="label">Last update</dt><dd>{s.last_success_at ? timeAgo(s.last_success_at) : "not yet run"}</dd></div>
                  {s.license && <div className="col-span-2 sm:col-span-1"><dt className="label">Terms</dt><dd>{s.license}</dd></div>}
                </dl>
              </li>
            ))}
            {data.sources.length === 0 && <li className="card text-slate-600">No sources are configured yet.</li>}
          </ul>
        </section>
      )}

      {data && (
        <section aria-labelledby="enrichment" className="space-y-3">
          <h2 id="enrichment" className="text-xl font-semibold">Maps, places and weather</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {data.enrichment.map((p) => (
              <li key={p.key} className="card text-sm">
                <h3 className="font-semibold">
                  <a href={p.homepage} target="_blank" rel="noopener noreferrer" className="hover:text-brand-700">{p.name}</a>
                </h3>
                <p className="text-slate-700">{p.purpose}</p>
                <p className="mt-2 text-xs text-slate-500">{p.attribution} · {p.license}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card space-y-2 text-sm text-slate-700">
        <h2 className="text-base font-semibold text-slate-900">Organizers</h2>
        <p>
          Found a mistake, or want your event listed or removed? Publishing schema.org <code>SportsEvent</code>{" "}
          markup on your website lets us pick up dates, prices and registration status automatically.
        </p>
        <p><a href="mailto:data@example.org" className="font-medium text-brand-700 underline">Contact the data team</a></p>
      </section>
    </div>
  );
}
