"use client";

import { useCallback, useEffect, useState } from "react";
import { InterviewSummary } from "@/components/ApplicationInterviewsPanel";
import { sendRequest } from "@/lib/apiErrors";
import { Interview, MY_INTERVIEWS_URL } from "@/lib/applicationInterviews";

// nehn-037 part 4 (DEC-SCOPE-296, AC3): the overseas student's admission interviews across their applications -- when, how, where and,
// once it has happened, the result. Read-only; the counselor records them.
export default function StudentInterviewsPanel() {
  const [items, setItems] = useState<Interview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    const outcome = await sendRequest(MY_INTERVIEWS_URL, {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setItems((outcome.data as unknown as { items: Interview[] }).items ?? []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="action-card">
      <h3>My interviews</h3>
      {loadError ? (
        <div className="form-error" role="alert">
          {loadError}{" "}
          <button type="button" className="btn ghost small" onClick={load}>
            Try again
          </button>
        </div>
      ) : items === null ? (
        <p className="muted">Loading interviews…</p>
      ) : items.length === 0 ? (
        <p className="muted">No admission interviews are scheduled yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {items.map((i) => (
            <li key={i.id} className="card" style={{ padding: 12 }}>
              <p style={{ margin: "0 0 4px" }}>
                <strong>{i.university}</strong> <span className="muted" style={{ fontSize: 13 }}>{i.application_code}</span>
              </p>
              <InterviewSummary interview={i} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
