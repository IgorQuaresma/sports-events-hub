import Link from "next/link";

export const metadata = { title: "Impressum & privacy" };

export default function LegalPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-3xl font-bold">Impressum &amp; privacy</h1>
      <p role="note" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        Placeholder. Before any public launch this page must contain the legally required Impressum (§ 5 DDG),
        a Datenschutzerklärung (Art. 13 DSGVO) and, if applicable, AGB. See docs/IMPLEMENTATION_PLAN.md §9.3.
      </p>
      <section className="space-y-2 text-sm text-slate-700">
        <h2 className="text-lg font-semibold text-slate-900">What this site stores</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>No user accounts, no tracking cookies, no third-party analytics.</li>
          <li>
            Clicks on “Register” are counted with a salted hash of IP address and browser that changes every day, so
            visits cannot be linked across days and no IP address is stored.
          </li>
          <li>
            “Use my location” is processed in your browser; only a rounded position (about 1&nbsp;km) is sent with the
            search request and it is not stored.
          </li>
          <li>Race-day weather is fetched by our server from Open-Meteo; your browser does not contact third parties.</li>
        </ul>
      </section>
      <section className="space-y-2 text-sm text-slate-700">
        <h2 className="text-lg font-semibold text-slate-900">Event data</h2>
        <p>
          Event information is collected from federations, open APIs and organizer websites (see{" "}
          <Link href="/sources" className="underline">data sources</Link>). Organizers can request corrections or
          removal at any time.
        </p>
      </section>
    </div>
  );
}
