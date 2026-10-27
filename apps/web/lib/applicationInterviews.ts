// nehn-037 part 4 (DEC-SCOPE-296): admission interviews on an overseas application. Mirrors apps/api/app/api/application_interviews.py;
// the server is the authority on every rule (I3: a result only after the date) and each role's scope.
import { localToIso, toLocalInput } from "@/lib/agentTasks";

export const INTERVIEW_MODES = ["online", "in_person", "phone"];
export const MODE_LABELS: Record<string, string> = { online: "Online", in_person: "In person", phone: "Phone" };
export const INTERVIEW_OUTCOMES = ["passed", "not_successful", "cancelled"];
export const OUTCOME_LABELS: Record<string, string> = { "": "Awaiting result", passed: "Passed", not_successful: "Not successful", cancelled: "Cancelled" };
export const LOCATION_MAX = 300;
export const NOTE_MAX = 500;

export type Interview = {
  id: string;
  application_id: string;
  scheduled_at: string;
  mode: string;
  mode_label: string;
  location: string | null;
  student_note: string | null;
  outcome: string | null;
  outcome_label: string;
  recorded_by?: string | null;
  university?: string;
  application_code?: string;
};

export type InterviewForm = { when: string; mode: string; location: string; student_note: string; outcome: string };

export const interviewsUrl = (applicationId: string) => `/api/v1/workflows/overseas/applications/${applicationId}/interviews`;
export const interviewUrl = (applicationId: string, interviewId: string) => `${interviewsUrl(applicationId)}/${interviewId}`;
export const MY_INTERVIEWS_URL = "/api/v1/workflows/overseas/student/interviews";

export const emptyForm = (): InterviewForm => ({ when: "", mode: "online", location: "", student_note: "", outcome: "" });

export const toForm = (i: Interview): InterviewForm => ({
  when: toLocalInput(i.scheduled_at),
  mode: i.mode,
  location: i.location ?? "",
  student_note: i.student_note ?? "",
  outcome: i.outcome ?? "",
});

// A link only when it is http(s); anything else (an address, "Room 4") is shown as text.
export function meetingLink(location: string | null): string | null {
  return location && /^https?:\/\/\S+$/i.test(location.trim()) ? location.trim() : null;
}

export function interviewProblem(form: InterviewForm, now: Date = new Date()): string | null {
  const iso = localToIso(form.when);
  if (!iso) return "Choose the interview date and time.";
  if (form.location.trim().length > LOCATION_MAX) return `The link or place must be ${LOCATION_MAX} characters or fewer.`;
  if (form.student_note.trim().length > NOTE_MAX) return `The note must be ${NOTE_MAX} characters or fewer.`;
  if ((form.outcome === "passed" || form.outcome === "not_successful") && Date.parse(iso) > now.getTime()) {
    return "A result can be recorded only after the interview date -- or mark it cancelled.";
  }
  return null;
}

// The request body: every field for a new interview, only the changed ones for an edit. Blank text and "awaiting" are null.
export function interviewBody(form: InterviewForm, saved?: Interview): Record<string, string | null> {
  const values: Record<string, string | null> = {
    scheduled_at: localToIso(form.when),
    mode: form.mode,
    location: form.location.trim() || null,
    student_note: form.student_note.trim() || null,
    outcome: form.outcome || null,
  };
  if (!saved) return values;
  const body: Record<string, string | null> = {};
  for (const [name, value] of Object.entries(values)) {
    const before = name === "scheduled_at" ? localToIso(toLocalInput(saved.scheduled_at)) : (saved[name as keyof Interview] ?? null);
    if (value !== before) body[name] = value;
  }
  return body;
}
