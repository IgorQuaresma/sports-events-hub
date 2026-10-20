/** Display helpers: one locale, human labels for every slug the API returns. */

export const LOCALE = "en-GB";

export const SPORTS: { slug: string; label: string; emoji: string }[] = [
  { slug: "triathlon", label: "Triathlon", emoji: "🏊" },
  { slug: "running", label: "Running", emoji: "🏃" },
  { slug: "trail-running", label: "Trail running", emoji: "⛰️" },
  { slug: "cycling", label: "Cycling", emoji: "🚴" },
  { slug: "swimming", label: "Open water", emoji: "🌊" },
  { slug: "ocr", label: "Obstacle (OCR)", emoji: "🧗" },
  { slug: "hyrox", label: "HYROX", emoji: "🏋️" },
  { slug: "hiking", label: "Hiking", emoji: "🥾" },
];
const SPORT_LABEL = Object.fromEntries(SPORTS.map((s) => [s.slug, s.label]));

export const COUNTRIES: Record<string, { label: string; flag: string }> = {
  DE: { label: "Germany", flag: "🇩🇪" },
  AT: { label: "Austria", flag: "🇦🇹" },
  CH: { label: "Switzerland", flag: "🇨🇭" },
  IT: { label: "Italy", flag: "🇮🇹" },
  FR: { label: "France", flag: "🇫🇷" },
  NL: { label: "Netherlands", flag: "🇳🇱" },
  US: { label: "United States", flag: "🇺🇸" },
};

export const REG_STATE: Record<string, { label: string; short: string; tone: "green" | "blue" | "amber" | "red" | "gray" }> = {
  open: { label: "Registration open", short: "Open", tone: "green" },
  not_open: { label: "Opens later", short: "Opens later", tone: "blue" },
  waitlist: { label: "Waitlist", short: "Waitlist", tone: "amber" },
  sold_out: { label: "Sold out", short: "Sold out", tone: "red" },
  closed: { label: "Registration closed", short: "Closed", tone: "gray" },
  unknown: { label: "Status unknown", short: "Unknown", tone: "gray" },
};

export const SOURCE_LABEL: Record<string, string> = {
  "world-triathlon": "World Triathlon",
  runsignup: "RunSignup",
  ticketmaster: "Ticketmaster",
  wikidata: "Wikidata + organizer site",
  sample: "Demo data",
};

export function humanize(slug: string): string {
  const s = slug.replace(/[-_]/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const sportLabel = (slug: string) => SPORT_LABEL[slug] ?? humanize(slug);
export const countryLabel = (code: string | null | undefined) =>
  code ? (COUNTRIES[code]?.label ?? code) : "";
export const regStateLabel = (state: string) => REG_STATE[state]?.label ?? humanize(state);
export const sourceLabel = (key: string) => SOURCE_LABEL[key] ?? humanize(key);
export const isDemo = (sourceKeys: string[] | undefined) => !!sourceKeys?.includes("sample");

/**
 * Discipline label from the taxonomy when available, else a readable slug. Slugs repeat across
 * sports ("relay", "long"), so names are keyed "sport:slug" with a slug-only fallback.
 */
export function disciplineLabel(slug: string, names?: Record<string, string>, sport?: string): string {
  return (sport && names?.[`${sport}:${slug}`]) || names?.[slug] || humanize(slug);
}

function toDate(iso: string): Date {
  // date-only strings are calendar days: anchor at noon to avoid timezone day-shifts
  return new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }): string {
  return toDate(iso).toLocaleDateString(LOCALE, opts);
}

export function formatDateRange(start: string, end?: string | null): string {
  if (!end || end === start) {
    return formatDate(start, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
  }
  const a = toDate(start);
  const b = toDate(end);
  const sameMonth = a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear();
  if (sameMonth) {
    return `${a.getDate()}–${b.toLocaleDateString(LOCALE, { day: "numeric", month: "long", year: "numeric" })}`;
  }
  return `${formatDate(start, { day: "numeric", month: "short" })} – ${formatDate(end)}`;
}

export function dateParts(iso: string): { day: string; month: string; weekday: string; year: string } {
  const d = toDate(iso);
  return {
    day: String(d.getDate()),
    month: d.toLocaleDateString(LOCALE, { month: "short" }),
    weekday: d.toLocaleDateString(LOCALE, { weekday: "short" }),
    year: String(d.getFullYear()),
  };
}

/** "today", "tomorrow", "in 12 days", "in 3 months", "5 days ago" */
export function relativeDay(iso: string, now = new Date()): string {
  const target = toDate(iso);
  const days = Math.round((target.getTime() - new Date(now.toDateString()).getTime()) / 86_400_000 - 0.5);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  const abs = Math.abs(days);
  const phrase = abs < 45 ? `${abs} days` : abs < 540 ? `${Math.round(abs / 30)} months` : `${Math.round(abs / 365)} years`;
  return days > 0 ? `in ${phrase}` : `${phrase} ago`;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const diff = (now - new Date(iso).getTime()) / 1000;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return `${Math.round(diff / 86400)} days ago`;
}

export function formatPrice(amount: string | number, currency: string | null | undefined): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "";
  try {
    return new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: currency || "EUR", maximumFractionDigits: n % 1 === 0 ? 0 : 2,
    }).format(n);
  } catch {
    return `${n} ${currency ?? ""}`.trim();
  }
}

const num = (n: number) => n.toLocaleString(LOCALE, { maximumFractionDigits: 1 });

export function formatDistances(d: Record<string, number>): string {
  const parts: string[] = [];
  if (d.swim_m) parts.push(`${d.swim_m >= 1000 ? `${num(d.swim_m / 1000)} km` : `${num(d.swim_m)} m`} swim`);
  if (d.bike_km) parts.push(`${num(d.bike_km)} km bike`);
  if (d.run_km) parts.push(`${num(d.run_km)} km run`);
  if (d.total_km && !d.run_km && !d.bike_km) parts.push(`${num(d.total_km)} km`);
  if (d.elevation_gain_m) parts.push(`${num(d.elevation_gain_m)} m ↑`);
  return parts.join(" · ");
}

/** Short, readable chips for the race conditions we know how to phrase. */
export function attributeChips(attrs: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(attrs)) {
    switch (k) {
      case "wetsuit_rule":
        out.push(
          { allowed: "Wetsuit allowed", mandatory: "Wetsuit mandatory", forbidden: "No wetsuit", depends_on_temperature: "Wetsuit: water temp." }[String(v)] ??
            `Wetsuit: ${humanize(String(v))}`,
        );
        break;
      case "course_profile":
        out.push(`${humanize(String(v))} course`);
        break;
      case "surface":
        out.push(`${humanize(String(v))} surface`);
        break;
      case "water_type":
        out.push(`${humanize(String(v))} swim`);
        break;
      case "elevation_gain_m":
        out.push(`${num(Number(v))} m elevation`);
        break;
      case "cutoff_minutes":
        out.push(`${Math.floor(Number(v) / 60)}h${String(Number(v) % 60).padStart(2, "0")} cut-off`);
        break;
      case "draft_legal":
        if (v === true) out.push("Draft legal");
        break;
      case "certified_course":
        if (v === true) out.push("Certified course");
        break;
    }
  }
  return out;
}

export function attributeRows(attrs: Record<string, unknown>): { label: string; value: string }[] {
  const LABELS: Record<string, string> = {
    wetsuit_rule: "Wetsuit", surface: "Surface", course_profile: "Course profile", water_type: "Water",
    draft_legal: "Draft legal", elevation_gain_m: "Elevation gain", cutoff_minutes: "Cut-off",
    certified_course: "Certified course",
  };
  return Object.entries(attrs).map(([k, v]) => ({
    label: LABELS[k] ?? humanize(k),
    value:
      typeof v === "boolean" ? (v ? "Yes" : "No")
        : k === "elevation_gain_m" ? `${num(Number(v))} m`
          : k === "cutoff_minutes" ? `${Math.floor(Number(v) / 60)} h ${Number(v) % 60} min`
            : humanize(String(v)),
  }));
}
