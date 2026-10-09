// upc-008 (DEC-SCOPE-143): a university's expected timeline (§5) and milestone tracker (§6). The API owns the catalogue, the Q-11 statuses
// and the auto-completed dates; these helpers only shape requests and word responses.
import { universityUrl } from "@/lib/universities";

export type MilestoneStatus = "done" | "in_progress" | "pending" | "delayed";
export type Milestone = {
  kind: string; label: string; target_date: string | null; achieved_on: string | null; achieved_by: "manual" | "auto" | null;
  auto_source: "stage" | "agreement" | "application" | "admission" | null; status: MilestoneStatus;
};
export type MilestonePage = { items: Milestone[]; today: string; can_edit: boolean };
export type UniversityExpected = {
  target_partnership_date: string | null; expected_month: string | null; expected_quarter: string | null; expected_intake: string | null;
  expected_agreement_date: string | null; expected_recruitment_start: string | null;
};
export type ExpectedField = "target_partnership_date" | "expected_intake" | "expected_agreement_date" | "expected_recruitment_start";

export const STATUS_LABEL: Record<MilestoneStatus, string> = { done: "Done", in_progress: "In progress", pending: "Pending", delayed: "Delayed" };
export const AUTO_LABEL: Record<NonNullable<Milestone["auto_source"]>, string> = {
  stage: "from the stage move", agreement: "from the signed agreement", application: "from the first application", admission: "from the first admission",
};
export const EXPECTED_FIELDS: { key: ExpectedField; label: string; type: "date" | "text" }[] = [
  { key: "target_partnership_date", label: "Target partnership date", type: "date" },
  { key: "expected_intake", label: "Expected intake", type: "text" },
  { key: "expected_agreement_date", label: "Expected agreement date", type: "date" },
  { key: "expected_recruitment_start", label: "Expected student recruitment start date", type: "date" },
];

export const milestonesUrl = (universityId: string, kind?: string) => universityUrl(universityId, kind ? `milestones/${kind}` : "milestones");
export const expectedUrl = (universityId: string) => universityUrl(universityId, "expected");

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const QUARTER_MONTHS = ["Jan–Mar", "Apr–Jun", "Jul–Sep", "Oct–Dec"];

/** "2026-11" -> "November 2026" (Q-10: derived by the API from the target partnership date). */
export function monthLabel(value: string | null): string | null {
  const m = value?.match(/^(\d{4})-(\d{2})$/);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : value;
}

/** "2026-Q4" -> "Q4 2026 (Oct–Dec)": calendar quarters. */
export function quarterLabel(value: string | null): string | null {
  const m = value?.match(/^(\d{4})-Q([1-4])$/);
  return m ? `Q${m[2]} ${m[1]} (${QUARTER_MONTHS[Number(m[2]) - 1]})` : value;
}

export function isMilestonePage(data: unknown): data is MilestonePage {
  const d = data as Partial<MilestonePage> | null;
  return !!d && typeof d === "object" && Array.isArray(d.items) && typeof d.today === "string";
}
