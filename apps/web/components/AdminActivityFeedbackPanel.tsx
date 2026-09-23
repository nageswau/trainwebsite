"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ActivityFeedbackDetails from "@/components/ActivityFeedbackDetails";
import LocalDateTime from "@/components/LocalDateTime";
import { type AdminActivityFeedback, activityTypeLabel, participationText } from "@/lib/activityFeedback";
import { isPage } from "@/lib/apiErrors";

// ENH-018 (spec §7.3): every school's activity feedback for Edusphere management, newest first. Loaded after first paint like
// the ENH-005 queue. Each feedback is a card (a <dl>) rather than a wide table, so long free text reflows on a phone. The school
// filter reuses GET /overseas-admin/schools; if that fails the list still works, unfiltered.
const LIMIT = 25;
type SchoolOption = { id: string; name: string };

export default function AdminActivityFeedbackPanel() {
  const [schools, setSchools] = useState<SchoolOption[]>([]);
  const [schoolId, setSchoolId] = useState("");
  const [items, setItems] = useState<AdminActivityFeedback[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState<"first" | "more" | null>("first");
  const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (school: string, offset: number, mode: "first" | "more") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode);
    if (mode === "first") setItems(null);
    try {
      const filter = school ? `school_id=${encodeURIComponent(school)}&` : "";
      const response = await fetch(`/api/v1/overseas-admin/school-activity-feedback?${filter}limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok || !isPage<AdminActivityFeedback>(data)) return setFailed(true);
      setFailed(false);
      setItems((prev) => (mode === "more" && prev ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setFailed(true);
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => {
    void load("", 0, "first");
    fetch("/api/v1/overseas-admin/schools")
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: unknown) => setSchools(Array.isArray(rows) ? rows.map((s: SchoolOption) => ({ id: s.id, name: s.name })) : []))
      .catch(() => setSchools([]));
    return () => controller.current?.abort();
  }, [load]);
  useEffect(() => {
    if (failed) alertRef.current?.focus();
  }, [failed]);

  function changeSchool(next: string) {
    setSchoolId(next);
    void load(next, 0, "first");
  }

  return (
    <div className="action-card wide">
      <div>
        <h3>{`School activity feedback${total > 0 ? ` (${total})` : ""}`}</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>What School Coordinators said after each Edusphere activity.</p>
      </div>
      <div className="table-controls">
        <div>
          <label htmlFor="feedback-school">School</label>
          <select id="feedback-school" className="select" value={schoolId} disabled={loading !== null} onChange={(e) => changeSchool(e.target.value)}>
            <option value="">All schools</option>
            {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>
      {failed && (
        <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
          <p style={{ margin: 0 }}>Could not load activity feedback.</p>
          <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load(schoolId, 0, "first")}>Try again</button>
        </div>
      )}
      {items === null && !failed ? (
        <div aria-busy="true">
          <p className="muted" style={{ margin: "0 0 8px" }}>Loading activity feedback…</p>
          <div className="skeleton-line" aria-hidden="true" />
        </div>
      ) : items !== null && items.length === 0 && !failed ? (
        <div className="empty"><h3>No feedback submitted yet.</h3></div>
      ) : items !== null && items.length > 0 ? (
        <>
          <p className="muted" aria-live="polite">{`Showing ${items.length} of ${total}`}</p>
          <ul className="link-list" role="list" aria-label="Activity feedback">
            {items.map((f) => (
              <li key={f.id} className="feedback-row">
                <div className="who">
                  <strong>{f.activity_title}</strong>
                  <span>
                    {f.school_name} · {activityTypeLabel(f.activity_type)} · <LocalDateTime value={f.scheduled_at} withTime /> · {participationText(f.participation)}
                  </span>
                </div>
                <ActivityFeedbackDetails feedback={f} />
              </li>
            ))}
          </ul>
          {items.length < total && (
            <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(schoolId, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>
          )}
        </>
      ) : null}
    </div>
  );
}
