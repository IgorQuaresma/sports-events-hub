import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <p className="text-sm font-semibold text-brand-700">404</p>
      <h1 className="mt-2 text-2xl font-semibold">We couldn&apos;t find that page</h1>
      <p className="mt-2 text-slate-600">
        The event may have been removed by its organizer, or the link is mistyped.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link href="/search" className="btn-primary">Search events</Link>
        <Link href="/" className="btn-secondary">Home</Link>
      </div>
    </div>
  );
}
