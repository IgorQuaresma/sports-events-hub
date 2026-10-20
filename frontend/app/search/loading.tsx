import { RaceCardSkeleton } from "@/components/RaceCard";

export default function Loading() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading search…</span>
      <div className="skeleton h-9 w-48" />
      <div className="skeleton h-11 w-full rounded-lg" />
      {[0, 1, 2, 3].map((i) => <RaceCardSkeleton key={i} />)}
    </div>
  );
}
