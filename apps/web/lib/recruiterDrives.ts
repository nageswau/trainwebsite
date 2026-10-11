// rec-029 (DEC-SCOPE-176): campus recruitment drives -- types, URLs, the form <-> body mapping (a PATCH sends only what changed), the
// form's own checks (AC2: attended <= registered) and the funnel's steps (Appendix B C2-C7). The API decides scope, re-checks every rule
// and computes the funnel; nothing here filters for security.
import type { ApplicationStatus } from "@/lib/recruiterApplications";
import { REQUIREMENTS_URL, type RequirementRow } from "@/lib/recruiterRequirements";
import type { LookupPage, PickOption } from "@/lib/lookups";

export type DriveStatus = "planned" | "completed" | "cancelled";
export type DriveCollege = { org_id: string | null; code: string | null; name: string; city: string | null };
export type DriveRow = {
  id: string; code: string; status: DriveStatus; status_label: string; drive_date: string; job_role: string; vacancies: number; eligibility: string | null;
  students_registered: number; students_attended: number; company: { id: string; code: string; name: string }; college: DriveCollege; can_edit: boolean;
  created_at: string; updated_at: string;
};
export type Funnel = { registered: number; attended: number; tagged: number; shortlisted: number; interviewed: number; selected: number; joined: number };
export type DriveRequirement = { id: string; code: string | null; title: string; status: string; open: boolean };
export type Drive = DriveRow & { funnel: Funnel; requirements: DriveRequirement[]; statuses: ApplicationStatus[] };
export type DriveList = { items: (DriveRow & { requirement_count: number })[]; total: number; limit: number; offset: number; can_create: boolean };
export type DriveCandidate = {
  application_id: string; candidate: { id: string; code: string; name: string }; requirement: { id: string; code: string | null; title: string };
  status: string; status_label: string;
};
export type DriveCandidates = { items: DriveCandidate[]; total: number; limit: number; offset: number };
export type DriveForm = {
  company: PickOption | null; requirements: PickOption[]; typed: boolean; college: PickOption | null; collegeName: string; drive_date: string;
  job_role: string; vacancies: string; eligibility: string; registered: string; attended: string; status: DriveStatus;
};

export const DRIVES_URL = "/api/v1/recruiter/drives";
export const DRIVES_PATH = "/recruiter/drives";
export const PAGE = 50;
export const STATUS_OPTIONS: { key: DriveStatus; label: string }[] = [
  { key: "planned", label: "Planned" }, { key: "completed", label: "Completed" }, { key: "cancelled", label: "Cancelled" },
];
export const driveUrl = (id: string) => `${DRIVES_URL}/${encodeURIComponent(id)}`;
export const drivePath = (id: string) => `${DRIVES_PATH}/${encodeURIComponent(id)}`;

export const EMPTY_DRIVE: DriveForm = {
  company: null, requirements: [], typed: true, college: null, collegeName: "", drive_date: "", job_role: "", vacancies: "", eligibility: "",
  registered: "0", attended: "0", status: "planned",
};

const WHOLE = /^\d{1,7}$/;
const squash = (text: string) => text.replace(/\s+/g, " ").trim();

export const collegeText = (c: DriveCollege) => (c.city ? `${c.name}, ${c.city}` : c.name);

const collegeOption = (c: DriveCollege): PickOption | null =>
  c.org_id ? { id: c.org_id, label: c.name, detail: [c.code, c.city].filter(Boolean).join(" · ") || null } : null;

export function formOf(d: Drive): DriveForm {
  return {
    company: { id: d.company.id, label: d.company.name, detail: d.company.code },
    requirements: d.requirements.map((r) => ({ id: r.id, label: r.title, detail: r.code })),
    typed: d.college.org_id === null, college: collegeOption(d.college), collegeName: d.college.org_id ? "" : d.college.name,
    drive_date: d.drive_date, job_role: d.job_role, vacancies: String(d.vacancies), eligibility: d.eligibility ?? "",
    registered: String(d.students_registered), attended: String(d.students_attended), status: d.status,
  };
}

/** The first thing the API would refuse, worded for the form; null when the form can be sent. */
export function formProblem(f: DriveForm): string | null {
  if (!f.company) return "Choose the company.";
  if (!f.requirements.length) return "Add at least one job requirement.";
  if (f.typed && !squash(f.collegeName)) return "Type the college name.";
  if (!f.typed && !f.college) return "Choose the college.";
  if (!f.drive_date) return "Choose the drive date.";
  if (!squash(f.job_role)) return "Enter the job role.";
  if (!WHOLE.test(f.vacancies) || Number(f.vacancies) < 1) return "Vacancies must be a whole number from 1.";
  if (!WHOLE.test(f.registered) || !WHOLE.test(f.attended)) return "Students registered and attended must be whole numbers.";
  if (Number(f.attended) > Number(f.registered)) return "Students attended cannot be more than students registered.";
  return null;
}

function fields(f: DriveForm): Record<string, unknown> {
  return {
    requirement_ids: f.requirements.map((r) => r.id),
    college_org_id: f.typed ? null : f.college?.id ?? null,
    college_name: f.typed ? squash(f.collegeName) || null : null,
    drive_date: f.drive_date, job_role: squash(f.job_role), vacancies: Number(f.vacancies), eligibility: f.eligibility.trim() || null,
    students_registered: Number(f.registered), students_attended: Number(f.attended), status: f.status,
  };
}

/** The POST body, or with `original` the PATCH body: only the changed keys, and both college keys whenever the college changed. */
export function driveBody(f: DriveForm, original?: DriveForm): Record<string, unknown> {
  const now = fields(f);
  if (!original) {
    delete now.status; // a new drive is always Planned
    return { company_id: f.company?.id, ...now };
  }
  const before = fields(original);
  const body: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(now)) if (JSON.stringify(value) !== JSON.stringify(before[key])) body[key] = value;
  if ("college_org_id" in body || "college_name" in body) Object.assign(body, { college_org_id: now.college_org_id, college_name: now.college_name });
  return body;
}

const STEPS: [keyof Funnel, string][] = [
  ["registered", "Registered"], ["attended", "Attended"], ["shortlisted", "Shortlisted"], ["interviewed", "Interviewed"], ["selected", "Selected"], ["joined", "Joined"],
];
export const funnelSteps = (f: Funnel): [string, number][] => STEPS.map(([key, label]) => [label, f[key]]);

/** The college picker: live BDM college / university organisations. */
export async function collegeSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${DRIVES_URL}/college-options?${query}`, { signal });
  if (!response.ok) throw new Error(`College search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; code: string; name: string; city: string }[]; total: number };
  return { items: page.items.map((o) => ({ id: o.id, label: o.name, detail: `${o.code} · ${o.city}` })), truncated: page.total > page.items.length };
}

/** The requirement picker: the company's live requirements (closed and cancelled ones left out). */
export function companyRequirementSearch(companyId: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20", company_id: companyId });
    if (q) query.set("q", q);
    const response = await fetch(`${REQUIREMENTS_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Requirement search failed (${response.status})`);
    const page = (await response.json()) as { items: RequirementRow[]; total: number };
    const live = page.items.filter((r) => r.status !== "closed" && r.status !== "cancelled");
    return { items: live.map((r) => ({ id: r.id, label: r.title, detail: r.code })), truncated: page.total > page.items.length };
  };
}

export function isDrive(data: unknown): data is Drive {
  const d = data as Partial<Drive> | null;
  return !!d && typeof d.id === "string" && typeof d.code === "string" && !!d.funnel && Array.isArray(d.requirements);
}

export function isDriveList(data: unknown): data is DriveList {
  const d = data as Partial<DriveList> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number" && typeof d.can_create === "boolean";
}

export function isDriveCandidates(data: unknown): data is DriveCandidates {
  const d = data as Partial<DriveCandidates> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number";
}
