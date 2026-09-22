"use client";

import { useEffect, useRef, useState } from "react";

import SchoolSkillAlert from "@/components/SchoolSkillAlert";
import { SkillStatus, useSkillAction } from "@/components/useSkillAction";
import { ENROLMENT_CLASS, ENROLMENT_LABEL, TRANSITIONS, attendanceText, type PortfolioStudent, type SkillBatchDetail, type SkillEnrollment, type SkillEnrollmentStatus } from "@/lib/skills";

// ENH-011 spec §7: the roster and the enrol picker. Only the changes the API allows are offered (TRANSITIONS); certifying asks first,
// because a certificate cannot be undone (D11). A student who has moved school is shown as such and cannot be changed (D9).
const BASE = "/api/v1/school/career-counselor";
const ACTION_LABEL: Record<SkillEnrollmentStatus, string> = { completed: "Mark completed", certified: "Certify", withdrawn: "Withdraw", enrolled: "Re-enrol" };
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function SchoolSkillEnrolments({ batch, students }: { batch: SkillBatchDetail; students: PortfolioStudent[] }) {
  const action = useSkillAction();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  // Browser QA-03: the focused button is removed when the confirmation opens, closes or a change succeeds, which dropped keyboard
  // focus to <body>. Whatever should take focus next is named here (a CSS selector inside this card) and focused after the render.
  const cardRef = useRef<HTMLDivElement>(null);
  const [focusNext, setFocusNext] = useState<string | null>(null);
  useEffect(() => {
    if (!focusNext) return;
    cardRef.current?.querySelector<HTMLElement>(focusNext)?.focus();
    setFocusNext(null);
  }, [focusNext]);
  const byLabel = (label: string) => `button[aria-label="${CSS.escape(label)}"]`;

  const enrolled = new Set(batch.enrollments.map((e) => e.school_student_id));
  const available = students.filter((s) => !enrolled.has(s.id));
  const shown = available.filter((s) => s.full_name.toLowerCase().includes(filter.trim().toLowerCase()));

  async function change(e: SkillEnrollment, to: SkillEnrollmentStatus) {
    setConfirming(null);
    setFocusNext(`th[data-enrolment="${e.id}"]`); // the row's own buttons change or disappear; keep focus on the row
    await action.run<SkillEnrollment>(`${BASE}/skill-enrollments/${e.id}`, "PATCH", { status: to }, (data) => `${e.student_name}: ${ENROLMENT_LABEL[data.status]}.`);
  }

  async function enrol() {
    const ids = available.filter((s) => picked.has(s.id)).map((s) => s.id);
    const rows = await action.run<SkillEnrollment[]>(`${BASE}/skill-batches/${batch.id}/enrollments`, "POST", { school_student_ids: ids }, (data) => `${plural(data.length, "student")} enrolled.`);
    if (rows) setPicked(new Set());
  }

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div ref={cardRef} className="card" aria-busy={action.busy}>
      <h2>Students</h2>
      <SkillStatus message={action.message} />
      <SchoolSkillAlert alert={action.alert} />
      {batch.enrollments.length === 0 ? (
        <p className="muted">No students enrolled yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Student</th><th scope="col">Status</th><th scope="col">Attendance</th><th scope="col">Change</th></tr></thead>
            <tbody>
              {batch.enrollments.map((e) => (
                <tr key={e.id}>
                  <th scope="row" tabIndex={-1} data-enrolment={e.id}>{e.student_name}</th>
                  <td>{e.frozen ? <span className="status pending">Transferred out</span> : <span className={ENROLMENT_CLASS[e.status]}>{ENROLMENT_LABEL[e.status]}</span>}</td>
                  <td>{attendanceText(e.attendance)}</td>
                  <td>
                    {e.frozen ? (
                      <span className="muted">Moved to another school; read-only here.</span>
                    ) : confirming === e.id ? (
                      <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                        Certify {e.student_name}? A certificate cannot be undone.
                        <button type="button" className="btn small" aria-label={`Confirm certify ${e.student_name}`} disabled={action.busy} onClick={() => void change(e, "certified")}>Confirm</button>
                        <button type="button" className="btn secondary small" onClick={() => { setConfirming(null); setFocusNext(byLabel(`Certify ${e.student_name}`)); }}>Cancel</button>
                      </span>
                    ) : (
                      <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 8 }}>
                        {TRANSITIONS[e.status].map((to) => (
                          <button key={to} type="button" className="btn secondary small" aria-label={`${ACTION_LABEL[to]} ${e.student_name}`} disabled={action.busy}
                            onClick={() => { if (to === "certified") { setConfirming(e.id); setFocusNext(byLabel(`Confirm certify ${e.student_name}`)); } else void change(e, to); }}>
                            {ACTION_LABEL[to]}
                          </button>
                        ))}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {batch.status === "open" && (
        students.length === 0 ? <p className="muted">No students at {batch.school.name} yet.</p>
        : available.length === 0 ? <p className="muted">Every student at {batch.school.name} is already enrolled.</p>
        : (
          <form className="form" onSubmit={(e) => { e.preventDefault(); void enrol(); }}>
            <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
              <legend><h3 style={{ margin: 0 }}>Enrol students</h3></legend>
              <div className="field">
                <label htmlFor="skill-enrol-filter">Filter students</label>
                <input id="skill-enrol-filter" type="search" className="search" value={filter} onChange={(e) => setFilter(e.target.value)} />
              </div>
              <div style={{ display: "grid", gap: 4, maxHeight: 320, overflow: "auto" }}>
                {shown.map((s) => (
                  <label key={s.id} style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44 }}>
                    <input type="checkbox" checked={picked.has(s.id)} disabled={action.busy} onChange={() => toggle(s.id)} />
                    {s.full_name}
                  </label>
                ))}
                {shown.length === 0 && <p className="muted">No student matches “{filter}”.</p>}
              </div>
            </fieldset>
            <button type="submit" className="btn" disabled={action.busy || picked.size === 0}>{action.busy ? "Enrolling…" : `Enrol ${plural(picked.size, "student")}`}</button>
          </form>
        )
      )}
    </div>
  );
}
