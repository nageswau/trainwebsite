// rec-007 (DEC-SCOPE-129): the Job Requirement -- types, endpoints and the pure helpers its list, form and detail share. The API scopes
// every row, decides every permission and lists the allowed status moves; nothing here filters for security.
import type { LookupPage } from "@/lib/lookups";
import { COMPANIES_URL, type Person, type Ref } from "@/lib/recruiterCompanies";

// hrc-007 (DEC-SCOPE-380 A1): Pending Approval and Filled.
export type Status =
  | "new" | "pending_approval" | "requirement_received" | "sourcing" | "shortlisting" | "profiles_shared" | "interviewing" | "selected" | "joined"
  | "filled" | "on_hold" | "closed" | "cancelled";
export const STATUS_KEYS: readonly Status[] = [
  "new", "pending_approval", "requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "filled",
  "on_hold", "closed", "cancelled",
];
/** hrc-007 (A2): the PDF's seven workflow phases; the API maps every status to one. */
export type Phase = "draft" | "pending_approval" | "open" | "on_hold" | "filled" | "closed" | "cancelled";
export type JobSource = "recruiter" | "employer" | "legacy";
export const SOURCE_LABEL: Record<JobSource, string> = { recruiter: "Recruiter", employer: "Employer", legacy: "Placement team" };
export type Option = { key: string; label: string };
export type RequirementPermissions = {
  can_edit: boolean; can_change_status: boolean; can_reassign: boolean; can_view_matches: boolean;
  can_manage_owners: boolean; can_view_candidates: boolean; // hrc-006 (DEC-SCOPE-384 O5)
};
export type CompanyRef = { id: string; code: string; name: string };
export type RequirementRow = {
  id: string; code: string; title: string; company: CompanyRef; location: string; status: Status; status_label: string; phase: Phase;
  phase_label: string; source: JobSource; visibility: Visibility; priority: string | null;
  vacancies: number | null; closes_on: string | null; requirement_date: string | null; deadline_state: "expiring" | "expired" | null;
  assigned_recruiter: Person | null; permissions: RequirementPermissions;
};
export type RequirementSkill = {
  id: string; name: string; kind: "required" | "preferred"; weight: number; skill_id: string | null; matched: boolean;
  min_level?: "beginner" | "intermediate" | "advanced" | "expert" | null; // hrc-017 (T9)
};
export type StatusChange = { from_status: string | null; from_label: string | null; to_status: string; to_label: string; note: string | null; changed_by: Person | null; created_at: string };
export type Requirement = RequirementRow & {
  description: string; department: string | null; job_category: Ref | null; qualification: string | null; experience_min_months: number | null;
  experience_max_months: number | null; salary_min: string | null; salary_max: string | null; work_mode: string | null; shift: string | null;
  employment_type: string | null; joining_requirement: string | null; skills: RequirementSkill[]; joined_count: number;
  allowed_statuses: Option[]; status_history: StatusChange[]; created_by: Person | null; created_at: string; updated_at: string;
  approval: Approval;
  // hrc-005 (DEC-SCOPE-381 V1/V6): the §4.2 fields and Last Updated By
  requisition_reference: string | null; lead_source: Ref | null; certifications: string | null; country: string | null; state: string | null;
  city: string | null; relocation_required: boolean | null; travel_requirement: string | null; salary_currency: string | null;
  salary_period: "year" | "month" | null; benefits: string | null; hiring_manager: Person | null; expected_joining_date: string | null;
  updated_by: Person | null;
  owners: Owner[]; // hrc-006: besides the primary (`assigned_recruiter`)
  visibility: VisibilityDetail; // hrc-008
  // pob-002 (DEC-SCOPE-407 R6/R7/R9): the hiring process, the terms (absent without commercials.client.view) and the backup owner
  backup_owner?: Person | null; interview_rounds?: string[]; screening_steps?: string[]; decision_maker?: DecisionMaker | null;
  expected_tat_days?: number | null; commercial_terms?: CommercialTerms;
};
export type DecisionMaker = { id: string; name: string; designation: string | null; active: boolean };
export type PaymentTrigger = "on_joining" | "days_after_joining" | "on_invoice";
export const PAYMENT_TRIGGER_OPTIONS: { id: PaymentTrigger; name: string }[] = [
  { id: "on_joining", name: "On joining" }, { id: "days_after_joining", name: "Days after joining" }, { id: "on_invoice", name: "On invoice" },
];
/** pob-002 R7: `inherited` = taken from the company's current contract. */
export type InheritedTerm = { value: string | null; inherited: boolean };
export type CommercialTerms = {
  fee: { basis: string | null; value: string | null; inherited: boolean }; payment_trigger: PaymentTrigger | null; payment_trigger_label: string | null;
  payment_days: number | null; payment_terms: InheritedTerm; replacement_terms: InheritedTerm; can_edit: boolean;
};
/** pob-002 R5: one revision in the list, and one revision read (its values and its changes against `compared_to`). */
export type RevisionField = { field: string; label: string };
export type RevisionItem = { revision: number; author: Person | null; reason: string | null; created_at: string; changed_fields: RevisionField[] };
export type RevisionPage = { items: RevisionItem[]; total: number; limit: number; offset: number };
export type RevisionValue = string | number | boolean | null;
export type RevisionDetail = Omit<RevisionItem, "changed_fields"> & {
  compared_to: number | null; values: (RevisionField & { value: RevisionValue })[];
  changes: (RevisionField & { before: RevisionValue; after: RevisionValue })[] | null;
};

/** A revision's stored value as text: empty is a dash, a yes/no reads as Yes/No, a vocabulary key as its label. */
export function revisionText(value: RevisionValue): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  return VOCABULARY_LABEL[value] ?? PAYMENT_TRIGGER_OPTIONS.find((o) => o.id === value)?.name ?? value;
}
/** hrc-008 (DEC-SCOPE-385 V1/V4): who sees the job; `can_change` = the caller holds `jobs.publish`. */
export type Visibility = "internal" | "portal" | "segment" | "public";
export type VisibilityDetail = { key: Visibility; label: string; segment_pool: Ref | null; can_change: boolean };
export const VISIBILITY_OPTIONS: { key: Visibility; label: string }[] = [
  { key: "public", label: "Public website" }, { key: "portal", label: "Candidate portal" },
  { key: "segment", label: "Segment (talent pool)" }, { key: "internal", label: "Internal only" },
];
export const VISIBILITY_HINT: Record<Visibility, string> = {
  public: "Listed on the careers page and in the student portal.",
  portal: "Listed in the student portal only, not on the public careers page.",
  segment: "Listed in the student portal only for members of one talent pool.",
  internal: "Seen by staff only. Candidates cannot see or apply to it.",
};
/** hrc-006 (DEC-SCOPE-384 O1/O2): a co-owner, and one ownership change (a primary change is two: removed, then added). */
export type OwnerRole = "placement_officer" | "collaborator";
export type Owner = { user: Person & { email: string }; role: OwnerRole; role_label: string; added_by: Person | null; added_at: string };
export type OwnerChange = {
  id: string; user: Person; role: "primary" | OwnerRole; role_label: string; action: "added" | "removed";
  reason: "reassign" | "deactivated" | "backfill" | null; changed_by: Person | null; created_at: string;
};
export type OwnerChangePage = { items: OwnerChange[]; total: number; limit: number; offset: number };
export const OWNER_ROLE_OPTIONS: readonly { key: OwnerRole; label: string }[] = [
  { key: "collaborator", label: "Collaborator" },
  { key: "placement_officer", label: "Placement officer owner" },
];
const REASON_TEXT = { reassign: " (reassignment)", deactivated: " (user deactivated)", backfill: " (recorded before ownership history)" } as const;

/** "Asha added Ravi as Collaborator" -- one history line, without the time. */
export function ownerChangeText(c: OwnerChange): string {
  const who = c.changed_by?.id === c.user.id ? "themselves" : c.user.full_name; // QA-01: "Rita added themselves", not "Rita added Rita"
  return `${c.changed_by?.full_name ?? "The system"} ${c.action} ${who} as ${c.role_label}${c.reason ? REASON_TEXT[c.reason] : ""}`;
}

/** The owner picker: eligible people not already on the requirement, searched on the server. */
export function ownerSearch(requirementId: string, role: OwnerRole | "backup") { // pob-002: `backup` = active recruiters for the backup owner
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ role, limit: "20" });
    if (q) query.set("q", q);
    const response = await fetch(`${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/assignment-options?${query}`, { signal });
    if (!response.ok) throw new Error(`Owner search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; full_name: string; email: string; role: string }[]; total: number };
    const kind = (r: string) => (r === "placement_officer" ? "Placement officer" : "Recruiter");
    return { items: page.items.map((u) => ({ id: u.id, label: u.full_name, detail: `${kind(u.role)} · ${u.email}` })), truncated: page.total > page.items.length };
  };
}
/** hrc-007 (A6/A8): whether the job still needs approval, who sent it, and what the caller may do about it. */
export type Approval = {
  required: boolean; submitted_by: Person | null; submitted_at: string | null; can_submit: boolean; can_decide: boolean;
};
export type ApprovalRow = RequirementRow & { description: string; submitted_by: Person | null; submitted_at: string | null; can_decide: boolean };
export type ApprovalSettings = { settings: Record<JobSource, boolean>; can_edit: boolean };
export const APPROVALS_URL = "/api/v1/recruiter/requirement-approvals";
export type StatusCatalogue = { statuses: (Option & { open: boolean; next: string[] })[]; vocabularies: Record<string, string[]>; expiring_days: number };

export const REQUIREMENTS_URL = "/api/v1/recruiter/requirements";
export const REQUIREMENTS_PATH = "/recruiter/requirements";
export const PRIORITY_LABEL: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };
export const VOCABULARY_LABEL: Record<string, string> = {
  onsite: "On-site", remote: "Remote", hybrid: "Hybrid", day: "Day", night: "Night", rotational: "Rotational", flexible: "Flexible",
  full_time: "Full time", part_time: "Part time", contract: "Contract", internship: "Internship", temporary: "Temporary", ...PRIORITY_LABEL,
};
export const DEADLINE_LABEL = { expiring: "Deadline soon", expired: "Deadline passed" } as const;

export const label = (value: string | null | undefined) => (value ? VOCABULARY_LABEL[value] ?? value : "—");

/** The form takes years (the source's "0–2 yrs"); the API stores whole months. Blank = null, anything else unreadable = NaN. */
export function monthsFromYears(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return Number.NaN;
  return Math.round(Number(trimmed) * 12);
}

export function yearsFromMonths(months: number | null): string {
  return months == null ? "" : String(Math.round((months / 12) * 100) / 100);
}

export function skillList(text: string): string[] {
  const seen = new Set<string>();
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase()));
}

/** pob-002 (R6): interview rounds or screening steps, one per line, in order; none = null (clears). */
export function stepList(text: string): string[] | null {
  const steps = text.split("\n").map((s) => s.trim()).filter(Boolean);
  return steps.length ? steps : null;
}

export function experienceText(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  if (min == null) return `Up to ${yearsFromMonths(max)} years`;
  if (max == null) return `${yearsFromMonths(min)}+ years`;
  return `${yearsFromMonths(min)}–${yearsFromMonths(max)} years`;
}

/** hrc-005: a null currency is rupees and a null period is a year (every row saved before the fields existed). */
export function salaryText(min: string | null, max: string | null, currency?: string | null, period?: string | null): string {
  if (min == null && max == null) return "—";
  const number = (value: string) => Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
  const money = (value: string) => (!currency || currency === "INR" ? `₹${number(value)}` : `${currency} ${number(value)}`);
  const per = period === "month" ? "a month" : "a year";
  if (min == null) return `Up to ${money(max!)} ${per}`;
  if (max == null) return `From ${money(min)} ${per}`;
  return `${money(min)} – ${money(max)} ${per}`;
}

/** hrc-005 (V5): a live requirement the server thinks the new or edited one may duplicate. */
export type DuplicateMatch = { id: string; code: string; title: string; location: string; status_label: string; requisition_reference: string | null };
export type PossibleDuplicate = { code: "possible_duplicate"; message: string; matches: DuplicateMatch[]; total: number };

/** The 409 `possible_duplicate` detail, or null for any other refusal. */
export function possibleDuplicate(detail: unknown): PossibleDuplicate | null {
  const d = detail as Partial<PossibleDuplicate> | null;
  return !!d && typeof d === "object" && d.code === "possible_duplicate" && Array.isArray(d.matches) ? (d as PossibleDuplicate) : null;
}

/** The form's fields, in screen order (EVID-018 §6). Experience is in years here (sent as months); skills are one per comma or line. */
export const FORM_FIELDS = [
  "requisition_reference", "lead_source_id", "title", "department", "job_category_id", "vacancies", "qualification", "experience_min_months",
  "experience_max_months", "certifications", "country", "state", "city", "location", "work_mode", "relocation_required", "travel_requirement",
  "salary_min", "salary_max", "salary_currency", "salary_period", "shift", "employment_type", "benefits", "hiring_manager_user_id",
  "joining_requirement", "expected_joining_date", "closes_on", "requirement_date", "priority", "required_skills", "preferred_skills",
  "description",
  // pob-002 (R6/R7/R9)
  "interview_rounds", "screening_steps", "decision_maker_contact_id", "expected_tat_days", "payment_trigger", "payment_days", "payment_terms",
  "replacement_terms", "backup_owner_user_id",
] as const;
const LIST_FIELDS = new Set<string>(["interview_rounds", "screening_steps"]);
const NUMBER_FIELDS = new Set<string>(["vacancies", "expected_tat_days", "payment_days"]);
export type FormField = (typeof FORM_FIELDS)[number];
export type FormValues = Record<FormField, string>;

export function valuesOf(r?: Requirement): FormValues {
  const text = (v: string | number | null | undefined) => (v == null ? "" : String(v));
  const skills = (kind: string) => (r?.skills ?? []).filter((s) => s.kind === kind).map((s) => s.name).join(", ");
  const terms = r?.commercial_terms;
  return {
    title: text(r?.title), department: text(r?.department), job_category_id: text(r?.job_category?.id), vacancies: text(r?.vacancies),
    qualification: text(r?.qualification), experience_min_months: yearsFromMonths(r?.experience_min_months ?? null),
    experience_max_months: yearsFromMonths(r?.experience_max_months ?? null), salary_min: text(r?.salary_min == null ? null : Number(r.salary_min)),
    salary_max: text(r?.salary_max == null ? null : Number(r.salary_max)), location: text(r?.location), work_mode: text(r?.work_mode),
    shift: text(r?.shift), employment_type: text(r?.employment_type), joining_requirement: text(r?.joining_requirement), closes_on: text(r?.closes_on),
    requirement_date: text(r?.requirement_date), priority: text(r?.priority), required_skills: skills("required"), preferred_skills: skills("preferred"),
    description: text(r?.description),
    // hrc-005
    requisition_reference: text(r?.requisition_reference), lead_source_id: text(r?.lead_source?.id), certifications: text(r?.certifications),
    country: text(r?.country), state: text(r?.state), city: text(r?.city),
    relocation_required: r?.relocation_required == null ? "" : r.relocation_required ? "yes" : "no", travel_requirement: text(r?.travel_requirement),
    salary_currency: text(r?.salary_currency), salary_period: text(r?.salary_period), benefits: text(r?.benefits),
    hiring_manager_user_id: text(r?.hiring_manager?.id), expected_joining_date: text(r?.expected_joining_date),
    // pob-002: one round or step per line; a term the contract supplies is blank (the requirement's own value is what is edited)
    interview_rounds: (r?.interview_rounds ?? []).join("\n"), screening_steps: (r?.screening_steps ?? []).join("\n"),
    decision_maker_contact_id: text(r?.decision_maker?.id), expected_tat_days: text(r?.expected_tat_days),
    payment_trigger: text(terms?.payment_trigger), payment_days: text(terms?.payment_days),
    payment_terms: terms && !terms.payment_terms.inherited ? text(terms.payment_terms.value) : "",
    replacement_terms: terms && !terms.replacement_terms.inherited ? text(terms.replacement_terms.value) : "",
    backup_owner_user_id: text(r?.backup_owner?.id),
  };
}

/** A form value as the API expects it: blank is null (clears on edit); numbers when they are numbers (else the server's 422 names it). */
export function wire(key: FormField, value: string): unknown {
  if (key === "required_skills" || key === "preferred_skills") return skillList(value);
  if (LIST_FIELDS.has(key)) return stepList(value);
  const trimmed = value.trim();
  if (trimmed === "") return key === "description" ? "" : null;
  if (key === "experience_min_months" || key === "experience_max_months") {
    const months = monthsFromYears(trimmed);
    return Number.isNaN(months) ? trimmed : months;
  }
  if (NUMBER_FIELDS.has(key) && /^\d+$/.test(trimmed)) return Number(trimmed);
  if (key === "relocation_required") return trimmed === "yes";
  if (key === "salary_currency") return trimmed.toUpperCase();
  return trimmed;
}

/** Create: every filled field. Edit: only the fields that changed. */
export function requirementBody(values: FormValues, original?: FormValues): Record<string, unknown> {
  const keys = FORM_FIELDS.filter((k) => (original ? values[k] !== original[k] : values[k].trim() !== ""));
  return Object.fromEntries(keys.map((k) => [k, wire(k, values[k])]));
}

export function isRequirementBody(data: unknown): data is { requirement: Requirement } {
  const requirement = (data as { requirement?: { id?: unknown } } | null)?.requirement;
  return !!requirement && typeof requirement.id === "string";
}

/** The company picker on "+ Add Job Requirement": the caller's companies, searched on the server (archived ones are left out). */
export async function companySearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${COMPANIES_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Company search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; code: string; name: string }[]; total: number };
  return { items: page.items.map((c) => ({ id: c.id, label: c.name, detail: c.code })), truncated: page.total > page.items.length };
}

/** hrc-005 (V2): the hiring-manager picker -- active internal interviewers, searched on the server. */
export async function hiringManagerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${REQUIREMENTS_URL}/hiring-managers?${query}`, { signal });
  if (!response.ok) throw new Error(`Hiring manager search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; full_name: string; email: string }[]; total: number };
  return { items: page.items.map((u) => ({ id: u.id, label: u.full_name, detail: u.email })), truncated: page.total > page.items.length };
}
