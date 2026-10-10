import type { PersonRef } from "@/lib/bdmTravel";
import { universityUrl } from "@/lib/universities";

// upc-023 (DEC-SCOPE-161): the §23 Expected University Partnerships list, the §24 probability and the weighted forecast (Appendix B E1-E4).
// The API decides who reads, the scope, the IST windows and every figure; these helpers only shape requests and word responses.
export type ExpectedWindowKey = "all" | "this_month" | "next_month" | "this_quarter" | "undated";
export type ForecastWindow = { key: ExpectedWindowKey; label: string; first: string; last: string; count: number; weighted: number };
export type ExpectedRow = {
  university: { id: string; university_code: string; name: string }; country: string; stage: string; stage_label: string;
  expected_agreement_date: string | null; owner: PersonRef | null; probability: number; stage_probability: number; override_reason: string | null;
};
export type ExpectedPage = {
  today: string; window: ExpectedWindowKey; windows: ForecastWindow[]; undated_count: number; total: number; limit: number; offset: number; items: ExpectedRow[];
};
export type UniversityProbability = { stage: number; override: number | null; reason: string | null; effective: number };

export const EXPECTED_URL = "/api/v1/partnership/expected";
export const EXPECTED_PATH = "/partnership/expected";
export const EXPECTED_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);
export const PAGE_SIZE = 25;
export const WINDOW_TABS: { key: ExpectedWindowKey; label: string }[] = [
  { key: "all", label: "All dated" },
  { key: "this_month", label: "This month" },
  { key: "next_month", label: "Next month" },
  { key: "this_quarter", label: "This quarter" },
  { key: "undated", label: "No expected date" },
];
const EMPTY: Record<ExpectedWindowKey, string> = {
  all: "No university has an expected agreement date yet.",
  this_month: "No partnership is expected this month.",
  next_month: "No partnership is expected next month.",
  this_quarter: "No partnership is expected this quarter.",
  undated: "Every university in progress has an expected agreement date.",
};

export const probabilityUrl = (universityId: string) => universityUrl(universityId, "probability");

/** The window in the URL; anything else is the full dated list. */
export function chosenWindow(value: string | undefined): ExpectedWindowKey {
  return WINDOW_TABS.some((t) => t.key === value) ? (value as ExpectedWindowKey) : "all";
}

export function expectedHref(window: ExpectedWindowKey, offset = 0): string {
  const q = new URLSearchParams();
  if (window !== "all") q.set("window", window);
  if (offset > 0) q.set("offset", String(offset));
  const query = q.toString();
  return query ? `${EXPECTED_PATH}?${query}` : EXPECTED_PATH;
}

export const emptyText = (window: ExpectedWindowKey) => EMPTY[window];

/** E4 in partnerships: "8" for a whole number, otherwise one decimal ("8.4"). */
export function weightedText(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** "40%", or "70% (override; stage 40%)" -- an override is never shown as if it were the stage's band. */
export function probabilityText(effective: number, stage: number, overridden: boolean): string {
  return overridden ? `${effective}% (override; stage ${stage}%)` : `${effective}%`;
}
