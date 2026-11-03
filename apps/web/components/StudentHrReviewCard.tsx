"use client";

import { useEffect, useState } from "react";

import { formatDay, MY_REVIEW_API, type StudentReview } from "@/lib/hrReviews";

// itc-027 (DEC-SCOPE-353 H7): the IT student's resume review on their Placement Status page -- the student-safe label, the action
// when HR asked for changes, and the date it last moved. The API sends nothing else (no internal stage, owner or notes).
export default function StudentHrReviewCard() {
  const [data, setData] = useState<StudentReview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(MY_REVIEW_API, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((body: StudentReview) => !cancelled && setData(body))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const status = data?.status;
  return (
    <section aria-labelledby="student-hr-review-heading" className="action-card" style={{ display: "grid", gap: 8 }}>
      <h3 id="student-hr-review-heading" style={{ margin: 0 }}>Resume review</h3>
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>Your resume review could not be loaded. Refresh the page to try again.</p>
      ) : !data ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading…</p>
      ) : !status ? (
        <p className="muted" style={{ margin: 0 }}>Share a resume with HR from your Profile page and HR will review it here.</p>
      ) : (
        <>
          <p style={{ margin: 0 }}><span className="badge">{status.label}</span>{status.updated_at && <span className="muted"> since {formatDay(status.updated_at)}</span>}</p>
          {status.action && <p style={{ margin: 0 }}>{status.action}</p>}
        </>
      )}
    </section>
  );
}
