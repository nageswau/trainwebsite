// rec-008 (DEC-SCOPE-132): a Job Requirement's JD -- types, endpoints and the pure helpers the JD section uses. The API scopes every
// read, numbers the versions and decides `can_edit`; nothing here filters for security.
import type { Person } from "@/lib/recruiterCompanies";
import { experienceText, type Requirement, REQUIREMENTS_URL, salaryText } from "@/lib/recruiterRequirements";

export type JdFile = { name: string | null; content_type: string; size_bytes: number };
export type JdVersion = {
  version: number; is_current: boolean; role: string; experience: string | null; qualification: string | null; skills: string | null;
  salary: string | null; location: string | null; description: string | null; responsibilities: string | null; requirements: string | null;
  openings: number | null; contact: { id: string; name: string; active: boolean } | null; closing_date: string | null;
  closing_date_differs: boolean; file: JdFile | null; created_by: Person | null; created_at: string;
};
export type Jd = { jd_number: string | null; versions: JdVersion[]; can_edit: boolean };

export const jdUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${requirementId}/jd`;
export const jdFileUrl = (requirementId: string, version: number) => `${jdUrl(requirementId)}/${version}/file`;
export const JD_ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const JD_MAX_BYTES = 5 * 1024 * 1024;

/** The form's fields in the EVID-018 §7 order (the company is the requirement's). */
export const JD_FIELDS = [
  "role", "experience", "qualification", "skills", "salary", "location", "description", "responsibilities", "requirements", "openings",
  "contact_id", "closing_date",
] as const;
export type JdField = (typeof JD_FIELDS)[number];
export type JdValues = Record<JdField, string>;
export const JD_LABEL: Record<JdField, string> = {
  role: "Job role", experience: "Experience", qualification: "Qualification", skills: "Skills", salary: "Salary", location: "Location",
  description: "Job description", responsibilities: "Responsibilities", requirements: "Requirements", openings: "Number of openings",
  contact_id: "Contact person", closing_date: "Closing date",
};
export const JD_MULTILINE: ReadonlySet<JdField> = new Set(["skills", "description", "responsibilities", "requirements"]);

const text = (v: string | number | null | undefined) => (v == null ? "" : String(v));
const orBlank = (v: string) => (v === "—" ? "" : v);

/** Edit from the current version; a first JD is prefilled from the requirement (experience, salary and skills written out as text). */
export function jdValues(current: JdVersion | undefined, r: Requirement): JdValues {
  if (current) {
    return {
      role: current.role, experience: text(current.experience), qualification: text(current.qualification), skills: text(current.skills),
      salary: text(current.salary), location: text(current.location), description: text(current.description),
      responsibilities: text(current.responsibilities), requirements: text(current.requirements), openings: text(current.openings),
      contact_id: text(current.contact?.id), closing_date: text(current.closing_date),
    };
  }
  return {
    role: r.title, experience: orBlank(experienceText(r.experience_min_months, r.experience_max_months)), qualification: text(r.qualification),
    skills: r.skills.map((s) => s.name).join(", "), salary: orBlank(salaryText(r.salary_min, r.salary_max)), location: text(r.location),
    description: text(r.description), responsibilities: "", requirements: "", openings: text(r.vacancies), contact_id: "",
    closing_date: text(r.closes_on),
  };
}

/** The whole version as the API expects it: blank is null; openings a number when it is one (else the server's 422 names it). */
export function jdBody(values: JdValues): Record<JdField, unknown> {
  return Object.fromEntries(
    JD_FIELDS.map((k) => {
      const trimmed = values[k].trim();
      if (trimmed === "") return [k, null];
      return [k, k === "openings" && /^\d+$/.test(trimmed) ? Number(trimmed) : trimmed];
    }),
  ) as Record<JdField, unknown>;
}

type Mapping = { label: string; field: string; jd: (v: JdVersion) => string | number | null; req: (r: Requirement) => string | number | null };
const MAPPINGS: Mapping[] = [
  { label: "Job title", field: "title", jd: (v) => v.role, req: (r) => r.title },
  { label: "Job location", field: "location", jd: (v) => v.location, req: (r) => r.location },
  { label: "Qualification", field: "qualification", jd: (v) => v.qualification, req: (r) => r.qualification },
  { label: "Number of vacancies", field: "vacancies", jd: (v) => v.openings, req: (r) => r.vacancies },
  { label: "Application deadline", field: "closes_on", jd: (v) => v.closing_date, req: (r) => r.closes_on },
  { label: "Job description", field: "description", jd: (v) => v.description, req: (r) => r.description || null },
];
export type RequirementChange = { label: string; from: string; to: string };

/** JD6: the requirement fields the JD would change (an empty JD field never clears one), and the PATCH that applies them. */
export function requirementChangesFromJd(v: JdVersion, r: Requirement): { changes: RequirementChange[]; patch: Record<string, unknown> } {
  const changes: RequirementChange[] = [];
  const patch: Record<string, unknown> = {};
  for (const m of MAPPINGS) {
    const next = m.jd(v);
    if (next == null || next === "" || next === m.req(r)) continue;
    changes.push({ label: m.label, from: text(m.req(r)) || "—", to: String(next) });
    patch[m.field] = next;
  }
  return { changes, patch };
}

/** JD8's warning, against the requirement as the page holds it now: the API's `closing_date_differs` was computed when the JD was
 * read, so it goes stale once "Update requirement from JD" copies the closing date over. */
export function closingDateDiffers(v: JdVersion, r: Requirement): boolean {
  return v.closing_date != null && v.closing_date !== r.closes_on;
}

export function isJd(data: unknown): data is Jd {
  return Array.isArray((data as Jd | null)?.versions);
}
