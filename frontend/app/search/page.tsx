import type { Metadata } from "next";
import { Suspense } from "react";
import { RaceCardSkeleton } from "@/components/RaceCard";
import { loadDisciplineNames } from "@/lib/taxonomy";
import SearchClient from "./SearchClient";

// rendered per request: labels come from the live taxonomy (itself cached for an hour)
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Search races",
  description: "Filter triathlons, runs, trail races, cycling and more by date, distance, location and registration status.",
};

export default async function SearchPage() {
  const names = await loadDisciplineNames();
  return (
    <Suspense
      fallback={
        <div className="space-y-3" aria-busy="true">
          <div className="skeleton h-9 w-48" />
          <div className="skeleton h-11 w-full rounded-lg" />
          {[0, 1, 2].map((i) => <RaceCardSkeleton key={i} />)}
        </div>
      }
    >
      <SearchClient disciplineNames={names} />
    </Suspense>
  );
}
