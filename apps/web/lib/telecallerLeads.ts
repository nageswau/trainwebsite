// tel-008 (DEC-SCOPE-084): the telecaller lead workspace -- types, labels and endpoints shared by My Leads and the lead detail. Labels
// are display only; the API decides scope, editability (`read_only`) and every rule.
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import type { Milestones } from "@/lib/leadHandover";

export type Priority = "hot" | "warm" | "cold";
export type PersonRef = { id: string; full_name: string };
export type TelecallerLead = {
  id: string; lead_code: string; name: string; email: string | null; phone: string | null; whatsapp_number: string | null; city: string | null;
  state: string | null; qualification: string | null; passing_year: number | null; institution: string | null; division: string; subject: string;
  status: string; status_label: string; source: string; priority: Priority; created_at: string; stage_changed_at: string;
  product: { id: string; name: string } | null; campaign: { id: string; name: string } | null; telecaller: PersonRef | null; counselor: PersonRef | null;
  read_only: boolean;
};
export type TelecallerLeadDetail = TelecallerLead & { message: string; milestones?: Milestones }; // tel-018: the linked student's milestones
export type TimelineRow = {
  id: string; kind: "stage" | "priority" | "enquiry"; at: string; actor: PersonRef | null; from_value: string; from_label: string; to_value: string;
  to_label: string; reason: string | null; event?: string | null; // tel-018: a stage row's pipeline event
};

/** tel-005 (R2): one lead of the §18 duplicate panel -- never its phone, email or messages. */
export type DuplicateMatch = {
  id: string; lead_code: string; name: string; status: string; status_label: string; telecaller: PersonRef | null; counselor: PersonRef | null;
  last_contact_at: string | null; matched_on: ("phone" | "email")[]; enquiries: { subject: string; source: string; at: string }[]; in_scope: boolean;
};

/** One activity row's title. tel-018 QA-03: a counselor's return is named, not shown as "Follow-up -> Follow-up". */
export function activityTitle(row: TimelineRow): string {
  if (row.kind === "enquiry") return `New enquiry: ${row.to_label}`;
  if (row.event === "returned") return "Returned to the telecaller";
  return `${row.kind === "priority" ? "Priority" : "Stage"}: ${row.from_label} → ${row.to_label}`;
}

export const LEADS_URL = "/api/v1/telecaller/leads";
export const DUPLICATE_CHECK_URL = `${LEADS_URL}/duplicate-check`;
export const leadUrl = (id: string, suffix = "") => `${LEADS_URL}/${encodeURIComponent(id)}${suffix}`;
export const TIMELINE_LIMIT = 50;
export const LEAD_LIST_FILTERS = ["status", "priority", "product_id", "campaign_id", "follow_up"] as const; // tel-011 F9: follow_up
export type LeadListFilter = (typeof LEAD_LIST_FILTERS)[number];
export const FOLLOW_UP_FILTERS = [{ key: "today", label: "Due today" }, { key: "overdue", label: "Overdue" }] as const;

// EVID-019 §8 (L316-L328): three levels, with the source's own help text.
export const PRIORITIES: { key: Priority; label: string; help: string }[] = [
  { key: "hot", label: "Hot", help: "Ready to join / immediate requirement." },
  { key: "warm", label: "Warm", help: "Interested but needs follow-up." },
  { key: "cold", label: "Cold", help: "Long-term / low interest." },
];
export const PRIORITY_LABEL: Record<string, string> = Object.fromEntries(PRIORITIES.map((p) => [p.key, p.label]));

/** A `tel:` link (T7): digits and one leading + only, so nothing else ever reaches the href; null when there is no usable number. */
export function telHref(phone: string | null): string | null {
  const compact = (phone ?? "").trim().replace(/[^\d+]/g, "");
  const digits = compact.replace(/\+/g, "");
  return digits.length >= 6 ? `tel:${compact.startsWith("+") ? "+" : ""}${digits}` : null;
}

/** tel-004's telecaller stage route ({to_stage, reason}); LeadStageControl calls it on the lead detail. */
export const moveStage = (id: string, target: string, reason: string): Promise<SendOutcome> =>
  sendJson(leadUrl(id, "/stage"), "POST", reason ? { to_stage: target, reason } : { to_stage: target });

// tel-009 (DEC-SCOPE-093, spec §3-§4): the qualification form. The API decides which fields apply (QD2); these lists only lay out the form.
export type ProductGroup = "it" | "overseas" | "other";
export type LeadQualification = {
  lead_id: string; product: { id: string; name: string; group: ProductGroup } | null; product_group: ProductGroup | null;
  qualification: string | null; passing_year: number | null; city: string | null; state: string | null; current_org: string | null;
  work_experience_years: number | null; it_skill_level: string | null; career_objective: string | null; preferred_batch: string | null;
  budget_range: string | null; preferred_mode: string | null; study_level: string | null; preferred_course: string | null; intake: string | null;
  academic_percentage: number | null; english_test_status: string | null; passport_status: string | null; read_only: boolean;
  updated_by: PersonRef | null; updated_at: string | null;
};
export type QualKey = Exclude<keyof LeadQualification, "lead_id" | "product" | "product_group" | "read_only" | "updated_by" | "updated_at">;
type Option = { value: string; label: string };
export type QualField =
  | { key: QualKey; label: string; kind: "text"; max: number }
  | { key: QualKey; label: string; kind: "number"; min: number; max: number; step: number; error: string }
  | { key: QualKey; label: string; kind: "select" | "radio"; options: Option[] };

const options = (pairs: [string, string][]): Option[] => pairs.map(([value, label]) => ({ value, label }));
// Appendix A L148-L196, in the source's order; lengths and ranges are the `lead_qualifications` / `enquiries` columns' (QF2).
export const BASIC_FIELDS: QualField[] = [
  { key: "qualification", label: "Qualification", kind: "text", max: 120 },
  { key: "current_org", label: "Current college/company", kind: "text", max: 200 },
  { key: "passing_year", label: "Passing year", kind: "number", min: 1950, max: 2100, step: 1, error: "Enter a year from 1950 to 2100." },
  { key: "work_experience_years", label: "Work experience (years)", kind: "number", min: 0, max: 50, step: 1, error: "Enter whole years from 0 to 50." },
  { key: "city", label: "City", kind: "text", max: 120 },
  { key: "state", label: "State", kind: "text", max: 120 },
];
export const REQUIREMENT: Record<"it" | "overseas", { legend: string; product: string; fields: QualField[] }> = {
  it: {
    legend: "IT training requirement", product: "Course interested in", fields: [
      { key: "it_skill_level", label: "Current skill level", kind: "select", options: options([["beginner", "Beginner"], ["intermediate", "Intermediate"], ["advanced", "Advanced"]]) },
      { key: "career_objective", label: "Career objective", kind: "text", max: 500 },
      { key: "preferred_batch", label: "Preferred batch", kind: "text", max: 120 },
      { key: "budget_range", label: "Budget range", kind: "text", max: 120 },
      { key: "preferred_mode", label: "Preferred mode", kind: "radio", options: options([["online", "Online"], ["offline", "Offline"]]) },
    ],
  },
  overseas: {
    legend: "Overseas requirement", product: "Destination", fields: [
      { key: "study_level", label: "UG / Master's", kind: "select", options: options([["ug", "UG"], ["masters", "Masters"]]) },
      { key: "preferred_course", label: "Preferred course", kind: "text", max: 200 },
      { key: "intake", label: "Intake", kind: "text", max: 40 },
      { key: "academic_percentage", label: "Academic percentage", kind: "number", min: 0, max: 100, step: 0.01, error: "Enter a percentage from 0 to 100." },
      { key: "english_test_status", label: "IELTS/PTE status", kind: "text", max: 120 },
      { key: "budget_range", label: "Budget", kind: "text", max: 120 },
      { key: "passport_status", label: "Passport status", kind: "select", options: options([["none", "No passport"], ["applied", "Applied"], ["valid", "Has a valid passport"]]) },
    ],
  },
};
export const qualificationUrl = (id: string) => leadUrl(id, "/qualification");
