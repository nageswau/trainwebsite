"use client";

import { useCallback, useEffect, useId, useState } from "react";

import FacultyCard from "./FacultyCard";
import { sendRequest } from "@/lib/apiErrors";
import { MY_FACULTY_API, type MyFacultyItem } from "@/lib/faculty";

/** itc-019 (DEC-SCOPE-345): the student's "My faculty" card on the Course page -- the trainer of each batch they are actively enrolled
 *  in, as much as each trainer chooses to show. */
export default function MyFaculty() {
  const [items, setItems] = useState<MyFacultyItem[] | null>(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const id = useId();

  const load = useCallback(async (signal: { cancelled: boolean }) => {
    setError(false);
    const outcome = await sendRequest(MY_FACULTY_API, { method: "GET" });
    if (signal.cancelled) return;
    const list = outcome.ok ? outcome.data.items : null;
    if (!Array.isArray(list)) return setError(true);
    setItems(list as MyFacultyItem[]);
  }, []);

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load, reload]);

  return (
    <section aria-labelledby={`${id}-title`} className="card" style={{ display: "grid", gap: 12, marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ margin: 0, fontSize: 18 }}>My faculty</h3>
      <div aria-live="polite" aria-busy={items === null && !error}>
        {error ? (
          <div role="alert" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <p className="form-error" style={{ margin: 0 }}>Unable to load your faculty.</p>
            <button type="button" className="btn secondary small" onClick={() => setReload((n) => n + 1)}>Try again</button>
          </div>
        ) : items === null ? (
          <p className="muted" style={{ margin: 0 }}>Loading your faculty…</p>
        ) : items.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>Your trainers appear here once you are enrolled in an active batch.</p>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 16 }}>
            {items.map((item) => (
              <li key={item.batch_id} style={{ display: "grid", gap: 8, paddingTop: 12, borderTop: "1px solid var(--border, #e5e7eb)" }}>
                <p className="eyebrow" style={{ margin: 0 }}>{item.program} · {item.batch}</p>
                {item.faculty ? <FacultyCard faculty={item.faculty} /> : <p className="muted" style={{ margin: 0 }}>Trainer not assigned yet.</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
