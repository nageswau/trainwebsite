"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import type { CertificateRules } from "@/lib/certificates";

// nehn-028 (DEC-SCOPE-308; docs/superpowers/specs/2026-10-27-nehn-028-trainer-progress-view-design.md): one batch's students against the
// certificate criteria, from `GET /workflows/it/batches/{id}/progress` -- the eligibility endpoint's own numbers, so nothing is
// re-derived here. A batch with no attendance yet shows "—", not 0%, and flags nobody.

type ProgressRow = {
  enrollment_id: string;
  student_code: string | null;
  student: string;
  enrollment_code: string;
  status: string;
  progress_percent: number;
  attendance_percent: number;
  attendance_sessions: number;
  at_risk: boolean;
  assignments_submitted: number;
  assignments_graded: number;
  assignments_total: number;
  assessments_passed: number;
  assessments_total: number;
  fee_clear: boolean;
  eligible: boolean;
  reasons: string[];
  certificate_issued: boolean;
};
type Progress = { rules: CertificateRules; students: ProgressRow[] };
type SortKey = "student" | "attendance" | "assignments" | "assessments" | "progress" | "eligible";

const LEFT = new Set(["dropped", "withdrawn"]);
const SORTS: Record<SortKey, (row: ProgressRow) => number | string> = {
  student: row => row.student.toLocaleLowerCase(),
  attendance: row => (row.attendance_sessions ? row.attendance_percent : -1),
  assignments: row => (row.assignments_total ? row.assignments_graded / row.assignments_total : 1),
  assessments: row => (row.assessments_total ? row.assessments_passed / row.assessments_total : 1),
  progress: row => row.progress_percent,
  eligible: row => (row.certificate_issued ? 2 : row.eligible ? 1 : 0),
};
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "student", label: "Student" },
  { key: "attendance", label: "Attendance" },
  { key: "assignments", label: "Assignments" },
  { key: "assessments", label: "Assessments" },
  { key: "progress", label: "Progress" },
  { key: "eligible", label: "Certificate" },
];

const label = (status: string) => status.charAt(0).toUpperCase() + status.slice(1).replace("_", " ");
const attendance = (row: ProgressRow) => (row.attendance_sessions ? `${row.attendance_percent}%` : "—");

function errorText(detail: unknown) {
  return typeof detail === "string" ? detail : "Student progress could not be loaded.";
}

export default function TrainerProgressPanel({ batches, loading = false, refreshKey = "" }: { batches: { id: string; name: string }[]; loading?: boolean; refreshKey?: string }) {
  const [batch, setBatch] = useState("");
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [riskOnly, setRiskOnly] = useState(false);
  const [showLeft, setShowLeft] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const selected = batches.some(item => item.id === batch) ? batch : batches[0]?.id ?? "";

  useEffect(() => {
    if (!selected) return;
    let current = true;
    setError("");
    fetch(`/api/v1/workflows/it/batches/${selected}/progress`)
      .then(async response => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(errorText(body.detail));
        if (current) setData(body as Progress);
      })
      .catch(failure => {
        if (current) {
          setData(null);
          setError(failure instanceof Error ? failure.message : "Student progress could not be loaded.");
        }
      });
    return () => {
      current = false;
    };
  }, [selected, refreshKey, attempt]);

  const current = useMemo(() => (data?.students ?? []).filter(row => !LEFT.has(row.status)), [data]);
  const rows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const shown = (data?.students ?? []).filter(
      row =>
        (showLeft || !LEFT.has(row.status)) &&
        (!riskOnly || row.at_risk) &&
        (!needle || row.student.toLocaleLowerCase().includes(needle) || (row.student_code ?? "").toLocaleLowerCase().includes(needle) || row.enrollment_code.toLocaleLowerCase().includes(needle)),
    );
    if (!sort) return shown;
    const value = SORTS[sort.key];
    return [...shown].sort((a, b) => {
      const left = value(a), right = value(b);
      const order = left < right ? -1 : left > right ? 1 : 0;
      return sort.direction === "asc" ? order : -order;
    });
  }, [data, query, riskOnly, showLeft, sort]);

  function changeSort(key: SortKey) {
    setSort(previous => (previous?.key === key ? { key, direction: previous.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" }));
  }

  function pickBatch(id: string) {
    setBatch(id);
    setData(null);
    setOpen(null);
  }

  let body;
  if (loading) body = <p className="muted">Loading your batches…</p>;
  else if (!batches.length) body = <p className="muted">No batch is assigned to you yet.</p>;
  else if (error)
    body = (
      <div className="form-error" role="alert">
        {error}{" "}
        <button type="button" className="btn small secondary" onClick={() => setAttempt(value => value + 1)}>Try again</button>
      </div>
    );
  else if (!data) body = <p className="muted" role="status">Loading student progress…</p>;
  else if (!data.students.length) body = <p className="muted">No students are enrolled in this batch yet.</p>;
  else {
    const atRisk = current.filter(row => row.at_risk).length;
    body = (
      <>
        <p className={atRisk ? "status pending" : "muted"} style={{ justifySelf: "start" }}>
          {atRisk} of {current.length} students below {data.rules.min_attendance_percent}% attendance
        </p>
        {rows.length ? (
          <div className="table-wrap">
            <table className="table trainer-progress-table">
              <caption className="visually-hidden">Student progress — select a column to sort</caption>
              <thead>
                <tr>
                  {COLUMNS.map(column => (
                    <th key={column.key} scope="col" aria-sort={sort?.key === column.key ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
                      <button className="sort-button" type="button" onClick={() => changeSort(column.key)}>
                        {column.label}
                        <span aria-hidden="true">{sort?.key === column.key ? (sort.direction === "asc" ? " ↑" : " ↓") : " ↕"}</span>
                      </button>
                    </th>
                  ))}
                  <th scope="col"><span className="visually-hidden">Details</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => {
                  const expanded = open === row.enrollment_id;
                  const detailsId = `progress-details-${row.enrollment_id}`;
                  return (
                    <Fragment key={row.enrollment_id}>
                      <tr className={LEFT.has(row.status) ? "inactive" : undefined}>
                        <th scope="row">
                          <strong>{row.student}</strong>
                          <span className="muted" style={{ display: "block", fontSize: 12, fontWeight: 400 }}>{[row.student_code, row.enrollment_code].filter(Boolean).join(" · ")}</span>
                          {row.status !== "active" && <span className="status pending">{label(row.status)}</span>}
                        </th>
                        <td>
                          {attendance(row)} {row.at_risk && <span className="status error">At risk</span>}
                        </td>
                        <td title="Submitted / graded / total">{`${row.assignments_submitted} / ${row.assignments_graded} / ${row.assignments_total}`}</td>
                        <td title="Passed / total">{`${row.assessments_passed} / ${row.assessments_total}`}</td>
                        <td>{`${row.progress_percent}%`}</td>
                        <td>
                          {row.certificate_issued ? <span className="status">Certificate issued</span> : row.eligible ? <span className="status">Eligible</span> : <span className="status error">Not eligible</span>}
                        </td>
                        <td>
                          <button type="button" className="btn small secondary" aria-expanded={expanded} aria-controls={expanded ? detailsId : undefined} aria-label={`Details for ${row.student}`} onClick={() => setOpen(expanded ? null : row.enrollment_id)}>
                            {expanded ? "Hide" : "Details"}
                          </button>
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="trainer-progress-details">
                          <td colSpan={COLUMNS.length + 1}>
                            <div id={detailsId} role="region" aria-label={`${row.student} progress details`}>
                              <ul>
                                <li>{row.attendance_sessions ? `Attendance: ${attendance(row)} of ${row.attendance_sessions} ${row.attendance_sessions === 1 ? "session" : "sessions"} recorded (needs ${data.rules.min_attendance_percent}%)` : `Attendance: no session recorded yet (needs ${data.rules.min_attendance_percent}%)`}</li>
                                <li>Assignments: {row.assignments_submitted} submitted, {row.assignments_graded} graded, of {row.assignments_total}</li>
                                <li>Assessments: {row.assessments_passed} passed of {row.assessments_total}</li>
                                <li>Progress: {row.progress_percent}% (needs {data.rules.min_progress_percent}%)</li>
                                <li>Fee: {row.fee_clear ? "clear" : "payment pending"}</li>
                              </ul>
                              {row.certificate_issued ? <p className="muted">A certificate has been issued.</p> : row.reasons.length ? (
                                <>
                                  <strong>Not yet eligible because:</strong>
                                  <ul>{row.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
                                </>
                              ) : <p className="muted">Meets every certificate criterion.</p>}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No student matches these filters.</p>
        )}
      </>
    );
  }

  return (
    <div className="action-card trainer-progress">
      <h3>Progress by student</h3>
      {batches.length > 0 && !loading && (
        <div className="table-controls" aria-label="Student progress controls">
          <div>
            <label htmlFor="progress-batch">Batch</label>
            <select id="progress-batch" className="select" value={selected} onChange={event => pickBatch(event.target.value)}>
              {batches.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <div className="table-control-search">
            <label htmlFor="progress-search">Search students</label>
            <input id="progress-search" className="search" type="search" placeholder="Name, student code or enrolment…" value={query} onChange={event => setQuery(event.target.value)} />
          </div>
          <label className="check"><input type="checkbox" checked={riskOnly} onChange={event => setRiskOnly(event.target.checked)} /> At risk only</label>
          <label className="check"><input type="checkbox" checked={showLeft} onChange={event => setShowLeft(event.target.checked)} /> Show dropped and withdrawn</label>
        </div>
      )}
      {body}
    </div>
  );
}
