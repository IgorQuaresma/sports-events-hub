import { api } from "./api";

/**
 * English discipline names from the taxonomy, keyed both "sport:slug" and "slug"
 * (see disciplineLabel). Falls back to an empty map — labels then come from the slug.
 */
export async function loadDisciplineNames(): Promise<Record<string, string>> {
  try {
    const t = await api.taxonomy();
    return Object.fromEntries(
      t.sports.flatMap((s) =>
        s.disciplines.flatMap((d) => [
          [d.slug, d.name.en ?? d.slug],
          [`${s.slug}:${d.slug}`, d.name.en ?? d.slug],
        ]),
      ),
    );
  } catch {
    return {};
  }
}
