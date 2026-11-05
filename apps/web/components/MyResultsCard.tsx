"use client";
import { useEffect, useState } from "react";

import { formatSchoolDateTime } from "@/lib/formatDate";
import { isMyResults, MY_RESULTS_URL, type MyResult } from "@/lib/interviewResults";

/** hrc-030 (DEC-SCOPE-409 R9): the candidate's (or IT student's) own interview results -- only those the company has published, with the
 *  message written for them. The API returns nothing that is still waiting for approval. */
export default function MyResultsCard() {
  const [items, setItems] = useState<MyResult[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(MY_RESULTS_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isMyResults(body) ? setItems(body.items) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [version]);

  return (
    <section className="action-card" aria-labelledby="my-results-heading" style={{ display: "grid", gap: 8 }}>
      <h3 id="my-results-heading" style={{ margin: 0 }}>My results</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load your results.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : items === null ? (
        <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading results…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>No interview results yet. A result appears here once the company publishes it.</p>
      ) : (
        <ul aria-label="My results" style={{ padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {items.map((r) => (
            <li key={r.id} style={{ listStyle: "none", display: "grid", gap: 2, overflowWrap: "anywhere" }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                <strong>{r.company}</strong>
                <span>{r.role}</span>
                <span className="badge">{r.outcome_label}</span>
              </div>
              <span className="muted" style={{ fontSize: 13 }}>{r.round} · Published {formatSchoolDateTime(r.released_at)}</span>
              <p style={{ margin: 0, whiteSpace: "pre-line" }}>{r.message}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
