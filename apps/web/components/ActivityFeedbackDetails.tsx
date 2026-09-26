import LocalTime from "@/components/LocalTime";
import { type ActivityFeedback, scoreText } from "@/lib/activityFeedback";
import { formatSchoolDateTime } from "@/lib/formatDate";

// ENH-018: one submitted feedback, read-only. Shared by the school list and the admin list. Free text renders as React text
// (escaped) and wraps inside its column, so a long unbroken word cannot widen the page. The submission time follows the date
// policy of the page it is on: India time in the school portal, the viewer's own zone on the admin list (a record time, so unlabelled).
export default function ActivityFeedbackDetails({ feedback, zone }: { feedback: ActivityFeedback; zone: "school" | "viewer" }) {
  return (
    <dl className="feedback-details">
      <dt>Overall rating</dt>
      <dd>{scoreText(feedback.rating)}</dd>
      <dt>School satisfaction</dt>
      <dd>{scoreText(feedback.satisfaction)}</dd>
      <dt>Trainer / Counsellor</dt>
      <dd>{feedback.trainer_name ?? "Not recorded"}</dd>
      <dt>Feedback</dt>
      <dd>{feedback.feedback}</dd>
      <dt>Suggestions</dt>
      <dd>{feedback.suggestions ?? "None"}</dd>
      <dt>Submitted by</dt>
      <dd>{feedback.submitted_by_name}, {zone === "school" ? formatSchoolDateTime(feedback.submitted_at) : <LocalTime value={feedback.submitted_at} time />}</dd>
    </dl>
  );
}
