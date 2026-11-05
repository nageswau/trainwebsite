// hrc-029 (DEC-SCOPE-405 V6/V7): the panel member's own interviews -- internal interviewers and employer users read the same API.
import type { PanelFeedback } from "@/lib/recruiterInterviews";

export type MyInterview = {
  id: string; code: string; round_label: string | null; round_number: number | null; scheduled_at: string; ends_at: string | null; mode: string;
  platform_label: string | null; meeting_url: string | null; location: string | null; phone_details: string | null; instructions: string | null;
  status: string; status_label: string; cancel_reason: string | null; is_lead: boolean;
  candidate: { code: string; name: string; location: string | null; qualification: string | null; experience_months: number | null; current_company: string | null; skills: string[] };
  requirement: { code: string | null; title: string }; company: { name: string };
  has_resume: boolean; feedback: PanelFeedback | null; can_feedback: boolean; feedback_overdue: boolean;
};
export type MyView = "upcoming" | "past";
export type MyInterviewsPage = { items: MyInterview[]; total: number; limit: number; offset: number; counts: Record<MyView, number> };

export const MY_VIEWS: [MyView, string][] = [["upcoming", "Upcoming"], ["past", "Past"]];
export const MY_INTERVIEWS_URL = "/api/v1/interviewer/interviews";
export const MY_LIMIT = 20;
export const NOTES_MAX = 2000;
export const ATTENDANCE: [PanelFeedback["attendance"], string][] = [["attended", "Attended"], ["no_show", "No-show"]];
export const RECOMMENDATIONS: [string, string][] = [["strong_yes", "Strongly recommend"], ["yes", "Recommend"], ["no", "Do not recommend"], ["strong_no", "Strongly do not recommend"]];

export const myInterviewsUrl = (view: MyView, offset = 0) => `${MY_INTERVIEWS_URL}?${new URLSearchParams({ view, limit: String(MY_LIMIT), offset: String(offset) })}`;
export const myInterviewUrl = (id: string, part?: "feedback" | "resume") => `${MY_INTERVIEWS_URL}/${encodeURIComponent(id)}${part ? `/${part}` : ""}`;

/** "2 yrs 3 mos" from months; null when unknown. */
export function experienceText(months: number | null): string | null {
  if (months === null) return null;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [years && `${years} yr${years === 1 ? "" : "s"}`, rest && `${rest} mo${rest === 1 ? "" : "s"}`].filter(Boolean);
  return parts.length ? parts.join(" ") : "Less than a month";
}

export function isMyInterview(data: unknown): data is MyInterview {
  const d = data as Partial<MyInterview> | null;
  return !!d && typeof d.id === "string" && typeof d.scheduled_at === "string" && !!d.candidate && typeof d.can_feedback === "boolean";
}
