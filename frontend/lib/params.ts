/** Pure helpers shared by server and client components (URL params, calendar days). */

export function isoDay(d: Date): string {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60_000);
  return z.toISOString().slice(0, 10);
}

export function datePresets(today = new Date()): { key: string; label: string; to: string | null }[] {
  const plus = (days: number) => isoDay(new Date(today.getTime() + days * 86_400_000));
  return [
    { key: "any", label: "Any time", to: null },
    { key: "30d", label: "Next 30 days", to: plus(30) },
    { key: "3m", label: "Next 3 months", to: plus(91) },
    { key: "6m", label: "Next 6 months", to: plus(182) },
  ];
}

export const listOf = (p: URLSearchParams, key: string) => (p.get(key) || "").split(",").filter(Boolean);
