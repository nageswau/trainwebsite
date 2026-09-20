"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition, type KeyboardEvent } from "react";
import SchoolPromotionRow, { isSettled, type PromotionAction, type PromotionRowResult, type PromotionStudent } from "@/components/SchoolPromotionRow";
import styles from "./SchoolPromotionPanel.module.css";

type ActiveYear = { id: string; label: string } | null;
type Report = { academic_year: { id: string; label: string }; counts: { promoted: number; held_back: number; failed: number; skipped: number }; results: PromotionRowResult[] };

const MAX_ITEMS = 500; // the API's per-request cap (spec §5.2)
const FILTER_ALL = "all";
const FILTER_UNSET = "unset";

const NOT_COMPLETED = "The request did not complete. Your selection is kept. Refresh to check the current state, then try again; repeating it is safe.";
const UNREADABLE = "The server's response could not be read, so it is unclear whether the changes were applied. Your selection is kept. Refresh to check the current state, then try again; repeating it is safe.";

// A 200 is only trusted if it has the shape of a report. A proxy login page or an empty body must not crash the screen.
function isReport(data: unknown): data is Report {
  const d = data as Partial<Report> | null;
  return !!d && typeof d === "object" && typeof d.academic_year?.label === "string" && Array.isArray(d.results) && typeof d.counts === "object" && d.counts !== null;
}

// Same two shapes SchoolStudentsPanel handles: a string `detail` (403/409) or FastAPI's list (422).
function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// ENH-004: the Coordinator's rollover screen. Choose students, review, confirm. Each selected student is
// promoted (grade + 1) or held back (same grade) into the ACTIVE academic year. Students already in that
// year are locked, so a second submit can never promote twice. Failed rows stay selected, with their
// reason beside the field, so the label can be corrected and retried.
export default function SchoolPromotionPanel({ students, activeYear }: { students: PromotionStudent[]; activeYear: ActiveYear }) {
  const router = useRouter();
  const [refreshing, startRefresh] = useTransition();
  const [filter, setFilter] = useState(FILTER_ALL);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [actions, setActions] = useState<Record<string, PromotionAction>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, PromotionRowResult>>({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const reviewRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);

  // Focus management: the confirm button takes focus when it appears, Cancel/Escape returns it to
  // "Review changes", and after a result or a failure the (now unmounted) confirm button's focus moves to the
  // summary or the error banner -- which also scrolls it into view from the bottom of a long list.
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      reviewRef.current?.focus();
    }
  }, [confirming]);
  useEffect(() => {
    if (summary) summaryRef.current?.focus();
  }, [summary]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const onSelect = useCallback((id: string, on: boolean) => {
    setSelected((prev) => ({ ...prev, [id]: on }));
    setConfirming(false);
  }, []);
  const onAction = useCallback((id: string, action: PromotionAction) => setActions((prev) => ({ ...prev, [id]: action })), []);
  const onOverride = useCallback((id: string, value: string) => setOverrides((prev) => ({ ...prev, [id]: value })), []);

  if (activeYear === null) {
    return (
      <div className="portal-content">
        <div className="card">
          <h2>Promote students</h2>
          <div className="empty" role="status">
            <h3>No active academic year</h3>
            <p>Promotion becomes available once an Overseas Admin activates the new academic year.</p>
          </div>
        </div>
      </div>
    );
  }

  const isLocked = (s: PromotionStudent) => s.academic_year_id === activeYear.id || isSettled(results[s.id]);
  const levels = Array.from(new Set(students.map((s) => s.grade_level).filter((l): l is number => l !== null))).sort((a, b) => a - b);
  const visible = students.filter((s) => filter === FILTER_ALL || (filter === FILTER_UNSET ? s.grade_level === null : String(s.grade_level) === filter));
  const selectable = visible.filter((s) => !isLocked(s));
  const chosen = students.filter((s) => selected[s.id] && !isLocked(s));
  const holdCount = chosen.filter((s) => actions[s.id] === "hold_back").length;
  const promoteCount = chosen.length - holdCount;
  const tooMany = chosen.length > MAX_ITEMS;
  const allShownSelected = selectable.length > 0 && selectable.every((s) => selected[s.id]);

  function changeFilter(value: string) {
    setFilter(value);
    setSelected({});
    setConfirming(false);
  }

  function toggleAllShown(on: boolean) {
    setSelected((prev) => {
      const next = { ...prev };
      for (const s of selectable) next[s.id] = on;
      return next;
    });
    setConfirming(false);
  }

  function cancelConfirm() {
    restoreFocus.current = true;
    setConfirming(false);
  }

  function onBarKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && confirming && !busy) cancelConfirm();
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setExpired(false);
    setSummary(null);
    const items = chosen.map((s) => {
      const action = actions[s.id] ?? "promote";
      const override = (overrides[s.id] || "").trim();
      return { student_id: s.id, action, ...(action === "promote" && override ? { grade_or_class: override } : {}) };
    });
    let response: Response;
    try {
      response = await fetch("/api/v1/school/students/promotions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }) });
    } catch {
      setBusy(false);
      setConfirming(false);
      setError(NOT_COMPLETED);
      return;
    }
    const data = await response.json().catch(() => null);
    setBusy(false);
    setConfirming(false);
    if (response.status === 401) {
      setExpired(true);
      setError("Your session has expired. Your selection is kept. ");
      return;
    }
    if (!response.ok) {
      setError(detailMessage(data?.detail));
      return;
    }
    if (!isReport(data)) {
      setError(UNREADABLE);
      return;
    }
    const report = data;
    const c = report.counts;
    setResults((prev) => ({ ...prev, ...Object.fromEntries(report.results.map((r) => [r.student_id, r])) }));
    setSelected(Object.fromEntries(report.results.filter((r) => r.status === "failed").map((r) => [r.student_id, true])));
    setSummary(`Done for ${report.academic_year.label}: ${c.promoted} promoted, ${c.held_back} held back, ${c.failed} not changed, ${c.skipped} skipped.`);
    startRefresh(() => router.refresh());
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Promote students</h2>
        <p>Move students into <span className="status">{activeYear.label}</span>, the active academic year. <strong>Promote</strong> advances the grade by one; <strong>Hold back</strong> keeps the grade and records the new year.</p>

        {error && <div ref={errorRef} tabIndex={-1} className="form-error" role="alert">{error}{expired && <Link href="/overseas/login">Sign in again</Link>}</div>}
        {summary && <div ref={summaryRef} tabIndex={-1} className={`form-message ${styles.summary}`} role="status">{summary}</div>}

        {students.length === 0 ? (
          <div className="empty">
            <h3>No students on the roster yet</h3>
            <p>Add students first, then come back to promote them.</p>
            <Link className="btn secondary small" href="/school/coordinator/students">Go to the student roster</Link>
          </div>
        ) : (
          <>
            <div className="table-controls" aria-label="Promotion filters">
              <div>
                <label htmlFor="promotion-filter">Grade level</label>
                <select id="promotion-filter" className={`select ${styles.filter}`} value={filter} disabled={busy} onChange={(e) => changeFilter(e.target.value)}>
                  <option value={FILTER_ALL}>All grades</option>
                  {levels.map((l) => <option key={l} value={String(l)}>Grade {l}</option>)}
                  <option value={FILTER_UNSET}>Grade level not set</option>
                </select>
              </div>
              <div>
                <label htmlFor="promotion-select-all">Select all shown</label>
                <input id="promotion-select-all" type="checkbox" checked={allShownSelected} disabled={busy || selectable.length === 0} onChange={(e) => toggleAllShown(e.target.checked)} />
              </div>
            </div>
            <p className="muted" aria-live="polite">Showing {visible.length} of {students.length} students</p>

            {visible.length === 0 ? (
              <div className="empty">
                <h3>No students match this filter</h3>
                <button type="button" className="btn secondary small" onClick={() => changeFilter(FILTER_ALL)}>Show all grades</button>
              </div>
            ) : (
              <ul className={styles.list} role="list" aria-busy={refreshing || busy}>
                <li className={styles.header} aria-hidden="true"><span>Student</span><span>Action</span><span>New label (optional)</span><span>Status</span></li>
                {visible.map((s) => (
                  <SchoolPromotionRow
                    key={s.id} student={s} activeYearLabel={activeYear.label} locked={isLocked(s)}
                    selected={!!selected[s.id]} action={actions[s.id] ?? "promote"} override={overrides[s.id] ?? ""} result={results[s.id] ?? null} busy={busy}
                    onSelect={onSelect} onAction={onAction} onOverride={onOverride}
                  />
                ))}
              </ul>
            )}

            <div className={styles.bar} onKeyDown={onBarKeyDown}>
              {confirming ? (
                <>
                  <p id="promotion-confirm-text" className={styles.barText}>Promote {promoteCount} and hold back {holdCount} into {activeYear.label}? This changes the current grade of each selected student.</p>
                  <div className={styles.barActions}>
                    <button ref={confirmRef} type="button" className="btn" onClick={submit} disabled={busy} aria-describedby="promotion-confirm-text">{busy ? "Promoting…" : "Confirm promotion"}</button>
                    <button type="button" className="btn ghost" onClick={cancelConfirm} disabled={busy}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <p id="promotion-selected-count" className={styles.barText}>{chosen.length} selected{tooMany ? `. Select at most ${MAX_ITEMS} at a time.` : ""}</p>
                  <button ref={reviewRef} type="button" className="btn" disabled={chosen.length === 0 || tooMany} aria-describedby="promotion-selected-count" onClick={() => setConfirming(true)}>Review changes ({chosen.length})</button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
