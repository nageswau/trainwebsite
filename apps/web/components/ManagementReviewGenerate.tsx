"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { monthLabel } from "@/lib/managementPlans";
import { finishedMonths, reviewApi, reviewHref } from "@/lib/managementReviews";
import { useHydrated } from "@/lib/useHydrated";

// mgmt-032 (MR4): generate the review of a finished month that has none yet (a missed beat run, or an earlier month). `today` is the
// IST date; the API checks the month again (422) and a month generated meanwhile simply opens.
export default function ManagementReviewGenerate({ today, reviewed }: { today: string; reviewed: string[] }) {
  const router = useRouter();
  const ready = useHydrated();
  const months = finishedMonths(today, reviewed);
  const [month, setMonth] = useState(months[0] ?? "");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one generate per double click

  if (months.length === 0) return <p className="muted">Every recent month already has a review.</p>;

  async function generate() {
    if (sending.current || !month) return;
    sending.current = true;
    setBusy(true);
    setMessage("");
    const result = await sendRequest(`${reviewApi(month)}/generate`, { method: "POST" });
    if (!result.ok && result.status !== 409) {
      setMessage(result.message);
      sending.current = false;
      setBusy(false);
      return;
    }
    router.push(reviewHref(month)); // 409: someone finalised it meanwhile -- open it
  }

  return (
    <form className="form action-card" noValidate aria-label="Generate a review" onSubmit={(e) => { e.preventDefault(); void generate(); }} style={{ marginBottom: 18 }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="field">
          <label htmlFor="review-month">Month</label>
          <select id="review-month" value={month} onChange={(e) => setMonth(e.target.value)} aria-describedby={message ? "review-month-error" : undefined}>
            {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
          {message && <p className="form-error" id="review-month-error" role="alert">{message}</p>}
        </div>
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Generating…" : "Generate review"}</button>
        </div>
      </fieldset>
    </form>
  );
}
