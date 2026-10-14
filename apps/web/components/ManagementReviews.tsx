import Link from "next/link";

import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { NONE, REVIEW_STATUS_CLASS, REVIEW_STATUS_LABEL, reviewHref, type ReviewPage } from "@/lib/managementReviews";

// mgmt-032 (MR3/MR4): every month's review, newest first. `data` is null when the read failed.
export default function ManagementReviews({ data, error }: { data: ReviewPage | null; error: string }) {
  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!data) return null;
  if (data.items.length === 0) return <p className="muted">No reviews yet. Each month&apos;s review is drafted on the 1st of the next month, or generate one above.</p>;
  return (
    <div className="table-wrap" role="region" aria-labelledby="reviews-title" tabIndex={0}>
      <table className="table stack">
        <caption className="visually-hidden" id="reviews-title">Monthly business reviews</caption>
        <thead>
          <tr><th scope="col">Month</th><th scope="col">Status</th><th scope="col">Figures taken</th><th scope="col">Finalised</th></tr>
        </thead>
        <tbody>
          {data.items.map((review) => (
            <tr key={review.month}>
              <th scope="row" data-label="Month"><Link className="kpi-link" href={reviewHref(review.month)}>{review.label}</Link></th>
              <td data-label="Status"><span className={REVIEW_STATUS_CLASS[review.status]}>{REVIEW_STATUS_LABEL[review.status]}</span></td>
              <td data-label="Figures taken">{formatDateTimeIn(review.generated_at, SCHOOL_TIME_ZONE)}</td>
              <td data-label="Finalised">{review.finalised_at ? formatDateTimeIn(review.finalised_at, SCHOOL_TIME_ZONE) : NONE}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
