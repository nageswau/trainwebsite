"use client";
import { useEffect, useState } from "react";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { isStudentOffers, salaryText, STUDENT_OFFERS_URL, studentLetterUrl, type StudentOffer } from "@/lib/recruiterOffers";

/** rec-022 (OF8): the student's own offers on their placement-status page -- company, position, status, salary, dates and the letter.
 *  The API returns only the caller's offers; downloads are plain links (the API audits each one). */
export default function StudentOffersCard() {
  const [items, setItems] = useState<StudentOffer[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(STUDENT_OFFERS_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isStudentOffers(body) ? setItems(body.items) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [version]);

  return (
    <section className="action-card" aria-labelledby="student-offers-heading" style={{ display: "grid", gap: 8 }}>
      <h3 id="student-offers-heading" style={{ margin: 0 }}>My offers</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load your offers.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : items === null ? (
        <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading offers…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>No offers yet.</p>
      ) : (
        <ul aria-label="My offers" style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {items.map((o) => {
            const salary = salaryText(o.compensation, o.currency);
            return (
              <li key={o.id} style={{ listStyle: "none", display: "grid", gap: 2, overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <strong>{o.company}</strong>
                  <span>{o.position ?? o.requirement}</span>
                  <span className="badge">{o.status_label}</span>
                </div>
                <span className="muted" style={{ fontSize: 13 }}>
                  {[salary, `Offered ${formatCalendarDate(o.offered_on)}`, o.joining_date && `Joining ${formatCalendarDate(o.joining_date)}`].filter(Boolean).join(" · ")}
                </span>
                {o.has_letter && <a href={studentLetterUrl(o.id)} download style={LINK_STYLE}>Download offer letter<span className="visually-hidden"> from {o.company}</span></a>}
                {!o.has_letter && o.letter_url && (
                  <a href={o.letter_url} target="_blank" rel="noopener noreferrer" style={LINK_STYLE}>Offer letter link<span className="visually-hidden"> (opens in a new tab)</span></a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
