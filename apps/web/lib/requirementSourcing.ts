// pob-017 (DEC-SCOPE-429): a requirement's sourcing plan and source funnel -- types, labels, endpoints and the form's body. The API decides every rule.
import { FIND_PATH, paramsOf, type SavedSearch, stateOfBody } from "@/lib/recruiterCandidateSearch";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

type Person = { id: string; full_name: string; active: boolean };
export type BooleanString = { label: string; query: string };
export type Stage = "found" | "screened" | "suitable" | "submitted" | "rejected";
export type FunnelCounts = Record<Stage, number> & { conversion: number | null };
export type FunnelRow = FunnelCounts & { source: { id: string; name: string; active: boolean }; planned: boolean };
export type ProgressState = "no_targets" | "met" | "on_track" | "breached";
export type Figure = { actual: number; target: number | null };
export type Sourcing = {
  plan: {
    target_profile: string | null; boolean_strings: BooleanString[]; target_found: number | null; target_screened: number | null; target_submitted: number | null;
    deadline: string | null; source_owner: Person | null; updated_by: Person | null; updated_at: string | null;
  };
  channels: { id: string; name: string; active: boolean }[];
  searches: SavedSearch[];
  hidden_searches: number;
  funnel: { rows: FunnelRow[]; total: FunnelCounts };
  progress: { state: ProgressState; short: string[]; deadline: string | null; days_left: number | null; found: Figure; screened: Figure; submitted: Figure };
  can_edit: boolean; can_link_searches: boolean;
};

export const STAGES: { key: Stage; label: string }[] = [
  { key: "found", label: "Found" },
  { key: "screened", label: "Screened" },
  { key: "suitable", label: "Suitable" },
  { key: "submitted", label: "Submitted" },
  { key: "rejected", label: "Rejected" },
];
export const TARGETS = [
  { key: "found", field: "target_found", label: "Profiles to find" },
  { key: "screened", field: "target_screened", label: "Profiles to screen" },
  { key: "submitted", field: "target_submitted", label: "Profiles to submit" },
] as const;
export const PROGRESS_LABELS: Record<ProgressState, string> = { no_targets: "No targets set", met: "Targets met", on_track: "In progress", breached: "Deadline missed" };
export const PROFILE_MAX = 2000;
export const LABEL_MAX = 80;
export const QUERY_MAX = 2000;
export const STRINGS_MAX = 10;
export const TARGET_MAX = 10000;

export const sourcingUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/sourcing`;
export const isSourcing = (body: unknown): body is Sourcing =>
  typeof (body as Sourcing | null)?.plan === "object" && Array.isArray((body as Sourcing).funnel?.rows) && typeof (body as Sourcing).progress === "object";

/** A linked saved search opens Find Candidates with its filters (the search lives in the URL). */
export const searchHref = (search: SavedSearch) => `${FIND_PATH}?${paramsOf(stateOfBody(search.filters)).toString()}`;

export const percent = (rate: number | null) => (rate === null ? "—" : `${Math.round(rate * 100)}%`);

export type Draft = {
  target_profile: string; boolean_strings: BooleanString[]; channel_ids: string[]; saved_search_ids: string[];
  target_found: string; target_screened: string; target_submitted: string; deadline: string; source_owner_user_id: string;
};

export function draftOf(data: Sourcing): Draft {
  const n = (v: number | null) => (v === null ? "" : String(v));
  return {
    target_profile: data.plan.target_profile ?? "", boolean_strings: data.plan.boolean_strings.map((s) => ({ ...s })),
    channel_ids: data.channels.map((c) => c.id), saved_search_ids: data.searches.map((s) => s.id),
    target_found: n(data.plan.target_found), target_screened: n(data.plan.target_screened), target_submitted: n(data.plan.target_submitted),
    deadline: data.plan.deadline ?? "", source_owner_user_id: data.plan.source_owner?.id ?? "",
  };
}

/** The PUT body, or the first problem a person can fix (checked again by the API). Empty Boolean rows are dropped. */
export function bodyOf(draft: Draft): { body: Record<string, unknown> } | { error: string } {
  const strings = draft.boolean_strings.map((s) => ({ label: s.label.trim(), query: s.query.trim() })).filter((s) => s.label || s.query);
  if (strings.some((s) => !s.label || !s.query)) return { error: "Give each search string both a name and the string itself." };
  const targets: Record<string, number | null> = {};
  for (const t of TARGETS) {
    const raw = draft[t.field].trim();
    if (raw && !/^\d+$/.test(raw)) return { error: `${t.label}: enter a whole number.` };
    const value = raw ? Number(raw) : null;
    if (value !== null && value > TARGET_MAX) return { error: `${t.label}: at most ${TARGET_MAX}.` };
    targets[t.field] = value;
  }
  return {
    body: {
      target_profile: draft.target_profile.trim() || null, boolean_strings: strings, channel_ids: draft.channel_ids, saved_search_ids: draft.saved_search_ids,
      ...targets, deadline: draft.deadline || null, source_owner_user_id: draft.source_owner_user_id || null,
    },
  };
}
