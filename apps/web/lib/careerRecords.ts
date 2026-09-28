// ENH-026 (DEC-SCOPE-031): one source for the counselling-record lifecycle and labels, used by the form and every read view.
export type CareerStatus = "not_started" | "scheduled" | "completed" | "follow_up_required";

export type CareerRecord = {
  id: string; school_student_id: string; record_type: string; notes: string; created_at: string; updated_at?: string;
  status?: CareerStatus | null; scheduled_for?: string | null; completed_on?: string | null; next_follow_up_date?: string | null;
  career_interests?: string[] | null; academic_strengths?: string[] | null; weak_areas?: string[] | null;
  recommended_careers?: string[] | null; recommended_courses?: string[] | null; recommended_stream?: string[] | null; recommended_skills?: string[] | null;
  global_education_interest?: boolean | null; parent_participated?: boolean | null; parent_participation_note?: string | null;
  counselor_name?: string | null; updated_by_name?: string | null;
};

export const CAREER_STATUS_LABEL: Record<CareerStatus, string> = {
  not_started: "Not Started", scheduled: "Scheduled", completed: "Completed", follow_up_required: "Follow-up Required",
};
export const NO_STATUS_LABEL = "No status (recorded before tracking)";
export const STRUCTURED_TYPES = ["guidance_session", "counselling_note"];
export const RECORD_TYPE_LABEL: Record<string, string> = { guidance_session: "Guidance session", counselling_note: "Counselling note", recommendation: "Recommendation" };

export const CAREER_LIST_FIELDS = [
  { key: "career_interests", label: "Career interests", group: "assessment" },
  { key: "academic_strengths", label: "Academic strengths", group: "assessment" },
  { key: "weak_areas", label: "Weak areas", group: "assessment" },
  { key: "recommended_careers", label: "Recommended careers", group: "recommendations" },
  { key: "recommended_courses", label: "Recommended courses", group: "recommendations" },
  { key: "recommended_stream", label: "Recommended subjects/stream", group: "recommendations" },
  { key: "recommended_skills", label: "Recommended skills", group: "recommendations" },
] as const;

const INITIAL: CareerStatus[] = ["not_started", "scheduled", "completed"];
const NEXT: Record<CareerStatus, CareerStatus[]> = {
  not_started: ["scheduled"], scheduled: ["completed"], completed: ["follow_up_required"], follow_up_required: ["scheduled", "completed"],
};

/** The statuses the API will accept from here (spec C2/C4): the three initial ones on create, else the current one plus its next states. */
export function statusOptions(current: CareerStatus | null | undefined, creating: boolean): CareerStatus[] {
  if (creating) return INITIAL;
  if (!current) return ["completed", "follow_up_required"];
  return [current, ...NEXT[current]];
}

export function statusLabel(status: CareerStatus | null | undefined): string {
  return status ? CAREER_STATUS_LABEL[status] : NO_STATUS_LABEL;
}
