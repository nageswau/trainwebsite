import { detailMessage } from "@/lib/apiErrors";

// AGN-007 (DEC-SCOPE-049): an agency's own universities and a student's university shortlist. The server is the authority; the
// checks here only spare a round trip (spec §6.3).
export const UNIVERSITIES_URL = "/api/v1/workflows/overseas/agent/crm/universities";
export const CATALOGUE_URL = "/api/v1/public/universities";
export const COUNTRIES_URL = "/api/v1/public/countries";
export const shortlistUrl = (studentId: string) => `/api/v1/workflows/overseas/agent/crm/students/${studentId}/shortlist`;
export const PAGE_SIZE = 20;

export type AgentUniversity = { id: string; name: string; country: string; city: string | null; entry_requirements: string | null; created_at: string; updated_at: string };
export type ShortlistEntry = {
  id: string;
  university: { source: "catalogue" | "agency"; id: string; name: string; slug: string | null; country: string | null };
  course: { id: string | null; title: string } | null;
  intake: string | null;
  tuition_fee: string | null;
  entry_requirements: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};
export type CatalogueCourse = { id: string; title: string; level: string; tuition_fee: string; intake: string };

// A university choice travels as "c:<id>" (catalogue) or "a:<id>" (agency) so one <select> holds both groups.
export type EntryDraft = { university: string; courseId: string; courseTitle: string; intake: string; tuitionFee: string; entryRequirements: string };
export type UniversityDraft = { name: string; country: string; city: string; entryRequirements: string };
type Payload = Record<string, string | null>;

export const LIMITS = { name: 200, country: 120, city: 120, course_title: 200, intake: 120, tuition_fee: 120, entry_requirements: 2000 } as const;

const universityKey = (source: "catalogue" | "agency", id: string) => `${source === "catalogue" ? "c" : "a"}:${id}`;
export function parseUniversityKey(key: string): { source: "catalogue" | "agency"; id: string } | null {
  const [kind, id] = key.split(":");
  if (!id || (kind !== "c" && kind !== "a")) return null;
  return { source: kind === "c" ? "catalogue" : "agency", id };
}

const clean = (value: string) => (value.trim() === "" ? null : value.trim());

// Browser QA-05: "Name — place", or just the name when there is no place (no dangling dash).
export const optionLabel = (name: string, place: string | null | undefined) => (place?.trim() ? `${name} — ${place}` : name);

// Browser QA-08: a server error (5xx) carries no useful detail, so it says to retry (the agency staff screens' wording, AGN-002/003).
const SERVER_FAILED = "The server couldn't complete this. Please try again in a moment.";
export function failureText(status: number, detail: unknown, fallback: string): string {
  return status >= 500 ? SERVER_FAILED : detailMessage(detail, fallback);
}

export const emptyEntryDraft = (): EntryDraft => ({ university: "", courseId: "", courseTitle: "", intake: "", tuitionFee: "", entryRequirements: "" });

export function draftFromEntry(e: ShortlistEntry): EntryDraft {
  return {
    university: universityKey(e.university.source, e.university.id),
    courseId: e.course?.id ?? "",
    courseTitle: e.course && !e.course.id ? e.course.title : "",
    intake: e.intake ?? "",
    tuitionFee: e.tuition_fee ?? "",
    entryRequirements: e.entry_requirements ?? "",
  };
}

export function buildEntryPayload(d: EntryDraft): Payload {
  const choice = parseUniversityKey(d.university);
  const catalogue = choice?.source === "catalogue";
  const courseId = catalogue && d.courseId ? d.courseId : null;
  return {
    university_id: catalogue ? choice!.id : null,
    agent_university_id: choice?.source === "agency" ? choice.id : null,
    course_id: courseId,
    course_title: courseId ? null : clean(d.courseTitle),
    intake: clean(d.intake),
    tuition_fee: clean(d.tuitionFee),
    entry_requirements: clean(d.entryRequirements),
  };
}

export function changedOnly(payload: Payload, original: Payload): Payload {
  return Object.fromEntries(Object.entries(payload).filter(([k, v]) => original[k] !== v));
}

const LABELS: Record<string, string> = { course_title: "Course", intake: "Intake", tuition_fee: "Tuition fee", entry_requirements: "Entry requirements", name: "Name", country: "Country", city: "City" };
function tooLong(fields: Record<string, string>): string | null {
  for (const [key, value] of Object.entries(fields)) {
    const limit = LIMITS[key as keyof typeof LIMITS];
    if (value.trim().length > limit) return `${LABELS[key]} must be ${limit} characters or fewer.`;
  }
  return null;
}

export function validateEntryDraft(d: EntryDraft): string | null {
  if (!parseUniversityKey(d.university)) return "Choose a university.";
  return tooLong({ course_title: d.courseTitle, intake: d.intake, tuition_fee: d.tuitionFee, entry_requirements: d.entryRequirements });
}

export function buildUniversityPayload(d: UniversityDraft): Payload {
  return { name: clean(d.name), country: clean(d.country), city: clean(d.city), entry_requirements: clean(d.entryRequirements) };
}

export function validateUniversityDraft(d: UniversityDraft): string | null {
  if (!d.name.trim()) return "Name is required.";
  if (!d.country.trim()) return "Country is required.";
  return tooLong({ name: d.name, country: d.country, city: d.city, entry_requirements: d.entryRequirements });
}
