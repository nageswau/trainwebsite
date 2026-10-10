// upc-025 (DEC-SCOPE-166): the Global Partnership Map -- its URL-held filters, the query it sends, the colour rule (Q-32) and the words it
// shows. The map counts exactly what the upc-024 search lists for the same filters (MP3), so a country links to that search plus `iso2`.
import { SEARCH_PATH } from "@/lib/universitySearch";

export const MAP_PATH = "/partnership/map";
export const MAP_URL = "/api/v1/partnership/universities/map";

export type MapCounts = { partner: number; in_progress: number; target: number; lost: number; total: number };
export type MapCountry = MapCounts & { iso2: string | null; name: string; region: string | null };
export type MapPage = { countries: MapCountry[]; totals: MapCounts; stages: { key: string; label: string }[] };
export type MapStatus = "partner" | "in_progress" | "target" | "lost";
export type MapColour = MapStatus | "none";

// The §2 filters (MP9), in the form's order; only these travel from the page URL to the API and on to the search.
export const MAP_KEYS = [
  "country", "region", "partner_status", "stage", "institution_type", "ranking_max", "ranking_system", "course", "level", "priority", "manager",
  "expected_from", "expected_to", "activity", "exclusivity",
] as const;
export type MapFilters = Partial<Record<(typeof MAP_KEYS)[number] | "view", string>>;

// Appendix B G1-G4, in the source's order and wording.
export const STATUS_LABELS: Record<MapStatus, string> = {
  partner: "Partner universities", in_progress: "Partnership in progress", target: "Target universities", lost: "Partnership lost / closed",
};
export const STATUS_ORDER: MapStatus[] = ["partner", "in_progress", "target", "lost"];
// The empty choice is "Active", the API's default (MP7), so an untouched form adds nothing to the URL.
export const ACTIVITY: Record<string, string> = { inactive: "Inactive", all: "Active and inactive" };
export const EXCLUSIVITY: Record<string, string> = { exclusive: "Exclusive", non_exclusive: "Non-exclusive" };

function params(filters: MapFilters, keys: readonly string[] = MAP_KEYS): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of keys) {
    const value = filters[key as keyof MapFilters]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export const mapQuery = (filters: MapFilters) => params(filters).toString();

/** This page with some filters (or the view) changed; an empty value removes one. */
export function mapHref(filters: MapFilters, changes: MapFilters = {}): string {
  const merged = { ...filters, ...changes };
  const query = params(merged);
  if (merged.view === "table") query.set("view", "table");
  const text = query.toString();
  return text ? `${MAP_PATH}?${text}` : MAP_PATH;
}

/** A country's university list: the search with the same filters, the exact country instead of the country text (MP4). */
export function countryHref(filters: MapFilters, iso2: string): string {
  const query = params(filters, MAP_KEYS.filter((key) => key !== "country"));
  query.set("iso2", iso2);
  return `${SEARCH_PATH}?${query.toString()}`;
}

/** Q-32 (MP11): the best status present wins -- partner, then in progress, then target, then lost; none when nothing matches. */
export function colourOf(row: MapCounts): MapColour {
  return STATUS_ORDER.find((status) => row[status] > 0) ?? "none";
}

export const countLabel = (row: MapCountry) =>
  `${row.name}: ${row.partner} partner, ${row.in_progress} in progress, ${row.target} target, ${row.lost} lost`;
