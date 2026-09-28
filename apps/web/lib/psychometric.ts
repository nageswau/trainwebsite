// ENH-027 -- the ten structured psychometric result fields (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §5).
// Shared by the server-rendered details and the client editor so neither imports the other; no server imports here (clientBoundary test).
// Lists use the product's comma convention (ENH-025/026: `splitList`/`listText`). Limits mirror the API (app/schemas.py
// PsychometricResultFields); the API stays the authority.
import { listText, splitList } from "@/lib/schoolStudents";

export const RESULT_LIST_FIELDS = [
  { key: "strengths", label: "Strengths" },
  { key: "interest_areas", label: "Interest areas" },
  { key: "personality_indicators", label: "Personality indicators" },
  { key: "recommended_careers", label: "Career recommendations" },
  { key: "recommended_stream", label: "Recommended streams" },
] as const;

export type ResultListKey = (typeof RESULT_LIST_FIELDS)[number]["key"];
type ResultTextKey = "test_date" | "counsellor_remarks" | "parent_discussion_on" | "parent_discussion_notes" | "follow_up_on";
export type ResultKey = ResultListKey | ResultTextKey;
export type PsychometricResult = Partial<Record<ResultListKey, string[] | null> & Record<ResultTextKey, string | null>>;
export type ResultDraft = Record<ResultKey, string>;

export const RESULT_KEYS: readonly ResultKey[] = [
  "test_date", "strengths", "interest_areas", "personality_indicators", "recommended_careers", "recommended_stream",
  "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
];
const LIST_KEYS: ReadonlySet<ResultKey> = new Set(RESULT_LIST_FIELDS.map((f) => f.key));

export const LIST_MAX_ITEMS = 20;
export const LIST_ITEM_MAX = 80;
export const REMARKS_MAX = 4000;
export const NOTES_MAX = 2000;

export function hasResults(r: PsychometricResult): boolean {
  return RESULT_KEYS.some((k) => {
    const v = r[k];
    return Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined && v !== "";
  });
}

export function toDraft(r: PsychometricResult): ResultDraft {
  return Object.fromEntries(RESULT_KEYS.map((k) => {
    const v = r[k];
    return [k, Array.isArray(v) ? listText(v) : (v ?? "")];
  })) as ResultDraft;
}

/** Only the fields the user changed (spec §4.3: last write wins per field, so unchanged fields are never re-sent). */
export function changedFields(initial: ResultDraft, draft: ResultDraft): Partial<Record<ResultKey, string | string[] | null>> {
  const out: Partial<Record<ResultKey, string | string[] | null>> = {};
  for (const k of RESULT_KEYS) {
    if (LIST_KEYS.has(k)) {
      const before = splitList(initial[k]);
      const after = splitList(draft[k]);
      if (JSON.stringify(before) !== JSON.stringify(after)) out[k] = after.length ? after : null;
    } else {
      const before = initial[k].trim();
      const after = draft[k].trim();
      if (before !== after) out[k] = after || null;
    }
  }
  return out;
}

export function listError(text: string): string | null {
  const items = splitList(text);
  if (items.length > LIST_MAX_ITEMS) return `Up to ${LIST_MAX_ITEMS} items.`;
  if (items.some((i) => i.length > LIST_ITEM_MAX)) return `Each item must be ${LIST_ITEM_MAX} characters or fewer.`;
  return null;
}
