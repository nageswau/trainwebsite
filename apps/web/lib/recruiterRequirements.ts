// rec-007 (DEC-SCOPE-125): the Job Requirement -- types, endpoints and the pure helpers its list, form and detail share. The API scopes
// every row, decides every permission and lists the allowed status moves; nothing here filters for security.
import type { LookupPage } from "@/lib/lookups";
import { COMPANIES_URL, type Person, type Ref } from "@/lib/recruiterCompanies";

export type Status =
  | "new" | "requirement_received" | "sourcing" | "shortlisting" | "profiles_shared" | "interviewing" | "selected" | "joined" | "on_hold" | "closed"
  | "cancelled";
export const STATUS_KEYS: readonly Status[] = [
  "new", "requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "on_hold", "closed", "cancelled",
];
export type Option = { key: string; label: string };
export type RequirementPermissions = { can_edit: boolean; can_change_status: boolean; can_reassign: boolean };
export type CompanyRef = { id: string; code: string; name: string };
export type RequirementRow = {
  id: string; code: string; title: string; company: CompanyRef; location: string; status: Status; status_label: string; priority: string | null;
  vacancies: number | null; closes_on: string | null; requirement_date: string | null; deadline_state: "expiring" | "expired" | null;
  assigned_recruiter: Person | null; permissions: RequirementPermissions;
};
export type RequirementSkill = { id: string; name: string; kind: "required" | "preferred"; weight: number; skill_id: string | null; matched: boolean };
export type StatusChange = { from_status: string | null; from_label: string | null; to_status: string; to_label: string; note: string | null; changed_by: Person | null; created_at: string };
export type Requirement = RequirementRow & {
  description: string; department: string | null; job_category: Ref | null; qualification: string | null; experience_min_months: number | null;
  experience_max_months: number | null; salary_min: string | null; salary_max: string | null; work_mode: string | null; shift: string | null;
  employment_type: string | null; joining_requirement: string | null; skills: RequirementSkill[]; joined_count: number;
  allowed_statuses: Option[]; status_history: StatusChange[]; created_by: Person | null; created_at: string; updated_at: string;
};
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

export function experienceText(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  if (min == null) return `Up to ${yearsFromMonths(max)} years`;
  if (max == null) return `${yearsFromMonths(min)}+ years`;
  return `${yearsFromMonths(min)}–${yearsFromMonths(max)} years`;
}

const rupees = (value: string) => `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export function salaryText(min: string | null, max: string | null): string {
  if (min == null && max == null) return "—";
  if (min == null) return `Up to ${rupees(max!)} a year`;
  if (max == null) return `From ${rupees(min)} a year`;
  return `${rupees(min)} – ${rupees(max)} a year`;
}

/** The form's fields, in screen order (EVID-018 §6). Experience is in years here (sent as months); skills are one per comma or line. */
export const FORM_FIELDS = [
  "title", "department", "job_category_id", "vacancies", "qualification", "experience_min_months", "experience_max_months", "salary_min",
  "salary_max", "location", "work_mode", "shift", "employment_type", "joining_requirement", "closes_on", "requirement_date", "priority",
  "required_skills", "preferred_skills", "description",
] as const;
export type FormField = (typeof FORM_FIELDS)[number];
export type FormValues = Record<FormField, string>;

export function valuesOf(r?: Requirement): FormValues {
  const text = (v: string | number | null | undefined) => (v == null ? "" : String(v));
  const skills = (kind: string) => (r?.skills ?? []).filter((s) => s.kind === kind).map((s) => s.name).join(", ");
  return {
    title: text(r?.title), department: text(r?.department), job_category_id: text(r?.job_category?.id), vacancies: text(r?.vacancies),
    qualification: text(r?.qualification), experience_min_months: yearsFromMonths(r?.experience_min_months ?? null),
    experience_max_months: yearsFromMonths(r?.experience_max_months ?? null), salary_min: text(r?.salary_min == null ? null : Number(r.salary_min)),
    salary_max: text(r?.salary_max == null ? null : Number(r.salary_max)), location: text(r?.location), work_mode: text(r?.work_mode),
    shift: text(r?.shift), employment_type: text(r?.employment_type), joining_requirement: text(r?.joining_requirement), closes_on: text(r?.closes_on),
    requirement_date: text(r?.requirement_date), priority: text(r?.priority), required_skills: skills("required"), preferred_skills: skills("preferred"),
    description: text(r?.description),
  };
}

/** A form value as the API expects it: blank is null (clears on edit); numbers when they are numbers (else the server's 422 names it). */
export function wire(key: FormField, value: string): unknown {
  if (key === "required_skills" || key === "preferred_skills") return skillList(value);
  const trimmed = value.trim();
  if (trimmed === "") return key === "description" ? "" : null;
  if (key === "experience_min_months" || key === "experience_max_months") {
    const months = monthsFromYears(trimmed);
    return Number.isNaN(months) ? trimmed : months;
  }
  if (key === "vacancies" && /^\d+$/.test(trimmed)) return Number(trimmed);
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
