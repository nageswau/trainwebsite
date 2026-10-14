import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementReview from "@/components/ManagementReview";
import ManagementReviewEditor from "@/components/ManagementReviewEditor";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import { ApiError, serverApi } from "@/lib/api";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import { isMonthKey, monthLabel } from "@/lib/managementPlans";
import { REVIEW_STATUS_CLASS, REVIEW_STATUS_LABEL, REVIEWS_HOME, reviewApi, type MonthlyReview } from "@/lib/managementReviews";

const UNAVAILABLE = "This review is unavailable right now. Please try again.";

// mgmt-032 (EVID-017 §32, MR5-MR14): one month's review -- the frozen sections 1-8, then the partners' §9/§10 (editable while a draft),
// and the same document as a PDF. Partners only; anyone else gets the access card. A malformed or ungenerated month says so.
export default async function ManagementReviewPage({ params }: { params: Promise<{ month: string }> }) {
  const { month } = await params;
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const back = <Link className="btn secondary" href={REVIEWS_HOME}>All reviews</Link>;
  const missing = (message: string) => (
    <DiscussionsShell me={me} section="Monthly business review" title="Review not found" actions={back}>
      <p>{message}</p>
    </DiscussionsShell>
  );
  if (!isMonthKey(month)) return missing("That is not a month. Choose a review from the list.");

  let review: MonthlyReview | null = null;
  let error = "";
  try {
    review = await serverApi<MonthlyReview>(reviewApi(month));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    if (e instanceof ApiError && e.status === 404) return missing(`There is no review for ${monthLabel(month)} yet. Generate it from the list once the month is over.`);
    error = UNAVAILABLE;
  }
  const at = (value: string) => formatDateTimeIn(value, SCHOOL_TIME_ZONE);
  return (
    <DiscussionsShell me={me} section="Monthly business review" title={`EduSphere Monthly Business Review — ${review?.label ?? monthLabel(month)}`} actions={back}
      intro={review && (
        <>
          Status: <span className={REVIEW_STATUS_CLASS[review.status]}>{REVIEW_STATUS_LABEL[review.status]}</span> · Figures taken {at(review.generated_at)}
          {review.finalised_at && <> · Finalised {at(review.finalised_at)}{review.finalised_by && ` by ${review.finalised_by.full_name}`}</>}
        </>
      )}>
      {error && <p className="form-error" role="alert">{error}</p>}
      {review && (
        <>
          <ReportDownloadButton url={`${reviewApi(month)}/pdf`} label="Download PDF" filename={`monthly-review-${month}.pdf`}
            hint="The PDF holds the same figures and answers as this page." />
          <p className="muted">Money is in Indian rupees. Figures are frozen as of when they were taken{review.status === "draft" ? "; regenerate them to take today's data." : "."}</p>
          <ManagementReview review={review} />
          <ManagementReviewEditor review={review} />
        </>
      )}
    </DiscussionsShell>
  );
}
