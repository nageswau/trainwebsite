import LocalDateTime from "@/components/LocalDateTime";
import { type ActivityFeedback, scoreText } from "@/lib/activityFeedback";

// ENH-018: one submitted feedback, read-only. Shared by the school list and the admin list. Free text renders as React text
// (escaped) and wraps inside its column, so a long unbroken word cannot widen the page.
export default function ActivityFeedbackDetails({ feedback }: { feedback: ActivityFeedback }) {
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
      <dd>{feedback.submitted_by_name}, <LocalDateTime value={feedback.submitted_at} withTime /></dd>
    </dl>
  );
}
