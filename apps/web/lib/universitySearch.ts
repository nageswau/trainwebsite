// upc-024 (DEC-SCOPE-163): the Global University Database -- its URL-held filters, the query it sends and the words it shows. The API is
// the gate: it ignores `commission_min` for every non-commission role (SR10), so hiding that field here is presentation only.
import type { Page } from "@/lib/apiErrors";
import type { UniversityRow } from "@/lib/universities";

export const SEARCH_PATH = "/partnership/search";
export const SEARCH_URL = "/api/v1/partnership/universities/search";

export const PARTNER_STATUSES: Record<string, string> = {
  partner: "Partner", in_progress: "Partnership in progress", target: "Target", not_partnered: "Not partnered", lost: "Lost / closed",
};

export type SearchRow = UniversityRow & {
  ownership_type: string | null; partner_status: "partner" | "in_progress" | "target" | "lost"; target_partnership_date: string | null;
  ranking: string | null; matching_courses: number | null;
};
export type SearchFacets = { partner_status: Record<"partner" | "in_progress" | "target" | "lost", number> };
export type SearchPage = Page<SearchRow> & { facets: SearchFacets };

// Only these keys travel from the page URL to the API (spec SR3-SR13), in the form's order. upc-025 added the map's iso2, stage,
// priority, activity and exclusivity (MP4-MP8), so a country link from the map lists exactly what the map counted.
export const SEARCH_KEYS = [
  "q", "country", "iso2", "region", "city", "institution_type", "ownership_type", "ranking_max", "ranking_system", "course", "level", "intake",
  "tuition_min", "tuition_max", "tuition_currency", "scholarship", "commission_min", "partner_status", "stage", "priority", "manager",
  "expected_from", "expected_to", "activity", "exclusivity",
] as const;
export type SearchFilters = Partial<Record<(typeof SEARCH_KEYS)[number] | "offset", string>>;

function params(filters: SearchFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of SEARCH_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function searchQuery(filters: SearchFilters, limit: number, offset: number): string {
  const query = params(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

/** A link to this search with some filters changed (an empty value removes one); any change but paging starts again at the first page. */
export function searchHref(filters: SearchFilters, changes: SearchFilters = {}, offset = 0): string {
  const query = params({ ...filters, ...changes });
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${SEARCH_PATH}?${text}` : SEARCH_PATH;
}

export const isFiltered = (filters: SearchFilters) => SEARCH_KEYS.some((key) => filters[key]?.trim());

/** The cross-field rules the API answers with a 422 (SR8, SR13), worded for the page so it can say what to fix. */
export function filterProblem(filters: SearchFilters): string | null {
  const min = filters.tuition_min?.trim(), max = filters.tuition_max?.trim();
  if ((min || max) && !filters.tuition_currency?.trim()) return "Choose a currency for the tuition range.";
  if (min && max && Number(min) > Number(max)) return "The lowest tuition is above the highest.";
  const from = filters.expected_from?.trim(), to = filters.expected_to?.trim();
  if (from && to && from > to) return "The expected date range ends before it starts.";
  return null;
}

/** The chips: each partner status with its count; "Not partnered" is target + in progress (SR11). */
export function statusCounts(facets: SearchFacets): [string, number][] {
  const f = facets.partner_status;
  return [
    ["", f.partner + f.in_progress + f.target + f.lost], ["partner", f.partner], ["in_progress", f.in_progress], ["target", f.target],
    ["not_partnered", f.in_progress + f.target], ["lost", f.lost],
  ];
}
