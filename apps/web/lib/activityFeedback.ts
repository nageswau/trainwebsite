// ENH-018 -- shapes of the activity-feedback API (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §5)
// and how its values are worded. A score or status is always shown as text, never as colour or a bare number.

export type Participation = { present: number; marked: number };

export type ActivityFeedback = {
  id: string;
  activity_id: string;
  trainer_name: string | null;
  rating: number;
  satisfaction: number;
  feedback: string;
  suggestions: string | null;
  submitted_by_name: string;
  submitted_at: string;
};

/** A row of the coordinator/principal list: an eligible activity and its feedback, or null while awaiting. */
export type FeedbackActivity = { activity_id: string; title: string; activity_type: string; scheduled_at: string; participation: Participation; feedback: ActivityFeedback | null };

export type AdminActivityFeedback = ActivityFeedback & { school_id: string; school_name: string; activity_title: string; activity_type: string; scheduled_at: string; participation: Participation };

export const FEEDBACK_FILTERS = [["all", "All"], ["awaiting", "Awaiting feedback"], ["submitted", "Submitted"]] as const;
export type FeedbackFilter = (typeof FEEDBACK_FILTERS)[number][0];

export const SCORE_LABELS = ["Poor", "Fair", "Good", "Very good", "Excellent"] as const;

// QA-018-14: a 401 is not a retryable failure. Same wording as ENH-005's transfer screens; each alert adds a "Sign in again" link.
export const SESSION_EXPIRED = "Your session has expired.";
export const SIGN_IN_PATH = "/overseas/login";

/** What a coordinator typed but could not save because the activity already had feedback (QA-018-03). Kept only in memory. */
export type UnsentText = { trainer_name: string | null; feedback: string; suggestions: string | null };

export const isFeedbackFilter = (value: unknown): value is FeedbackFilter => FEEDBACK_FILTERS.some(([v]) => v === value);

/** Why a list could not be shown: the session ended (sign in again) or the load failed (try again). */
export type LoadFailure = "expired" | "failed" | null;

// Same wording as the Activities scheduling form's category options (SchoolActivitiesPanel).
const ACTIVITY_TYPES: Record<string, string> = {
  career_seminar: "Career seminar",
  career_awareness_session: "Student career awareness session",
  parent_orientation: "Parent orientation",
  campus_visit: "Monthly campus visit",
};

export const activityTypeLabel = (type: string) => ACTIVITY_TYPES[type] ?? type;
export const participationText = (p: Participation) => (p.marked === 0 ? "Not marked" : `${p.present} of ${p.marked} present`);
export const scoreText = (n: number) => `${n} – ${SCORE_LABELS[n - 1] ?? ""}`.trim();

/** Mirrors the API's rule (spec D1/D7) so the Activities list only offers the link where the POST can succeed. */
export function isFeedbackEligible(activity: { activity_type?: string | null; scheduled_at: string }, now = Date.now()): boolean {
  return !!activity.activity_type && Date.parse(activity.scheduled_at) <= now;
}
