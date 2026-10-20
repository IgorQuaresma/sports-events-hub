export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading event…</span>
      <div className="skeleton h-4 w-40" />
      <div className="space-y-3">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-9 w-2/3" />
        <div className="skeleton h-4 w-1/2" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-32 w-full rounded-xl" />)}
        </div>
        <div className="skeleton h-64 w-full rounded-xl" />
      </div>
    </div>
  );
}
