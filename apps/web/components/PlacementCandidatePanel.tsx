"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type CandidateRow = {
  student_id: string;
  student: string;
  email: string;
  skills: string[];
  readiness_status: string;
  resume_status: string;
  mock_interview_status: string;
  aptitude_status: string;
  available: boolean;
  withdrawn: boolean;
  notes: string | null;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update candidate.";
}

// ADM-007: "Placement Team manages the domestic placement pipeline." The only existing
// write path was a generic form requiring the student's raw database reference typed by
// hand -- same class of gap already fixed for ADM-001/002/003/004/006. Also, no
// "withdrawn" concept existed anywhere: `available` only ever meant "temporarily
// unavailable," so a genuinely withdrawn candidate stayed in the active pool forever
// (ADM-007-AC02 violation). Real picker + a two-step withdraw/reinstate control, same
// pattern as `AdminUserManagementPanel`'s activate/deactivate toggle. Withdrawn
// candidates are excluded from `GET .../placement/profiles` by default (this component's
// own data source), so this list itself already only shows the active pool.
export default function PlacementCandidatePanel() {
  const router = useRouter();
  const [rows, setRows] = useState<CandidateRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function load() {
    fetch("/api/v1/workflows/it/placement/profiles")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setRows(data))
      .catch(() => setRows([]));
  }

  useEffect(load, []);

  const visible = useMemo(() => {
    if (!rows) return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((r) => r.student.toLowerCase().includes(normalized) || r.email.toLowerCase().includes(normalized));
  }, [rows, query]);

  async function save(row: CandidateRow, body: Record<string, unknown>, successText: string) {
    setBusyId(row.student_id);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/it/placement/profiles/${row.student_id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.student_id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: row.student_id, text: successText, failed: false });
    setEditingId(null);
    load();
    router.refresh();
  }

  async function withdraw(row: CandidateRow) {
    await save(
      row,
      { readiness_status: row.readiness_status, resume_status: row.resume_status, mock_interview_status: row.mock_interview_status, aptitude_status: row.aptitude_status, available: row.available, withdrawn: !row.withdrawn },
      row.withdrawn ? `${row.student} reinstated to the active pool.` : `${row.student} withdrawn from the active pool.`
    );
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Candidate pool</h3>
        <p className="muted">Loading candidates…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Candidate pool</h3>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="placement-candidate-search">Search by name or email</label>
        <input id="placement-candidate-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {visible.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{rows.length === 0 ? "No candidates in the active pool." : "No candidates match this search."}</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Readiness</th>
                <th scope="col">Available</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.student_id}>
                  <th scope="row">{row.student}<br /><span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{row.email}</span></th>
                  <td>{row.readiness_status}</td>
                  <td>{row.available ? "Yes" : "No"}</td>
                  <td>
                    <button className="btn small" disabled={busyId === row.student_id} onClick={() => setEditingId(editingId === row.student_id ? null : row.student_id)}>
                      {editingId === row.student_id ? "Cancel" : "Edit"}
                    </button>{" "}
                    <button className="btn small secondary" disabled={busyId === row.student_id} onClick={() => void withdraw(row)}>
                      {busyId === row.student_id ? "Saving…" : "Withdraw from pool"}
                    </button>
                    {editingId === row.student_id && (
                      <form
                        className="form"
                        style={{ marginTop: 10 }}
                        onSubmit={(event) => {
                          event.preventDefault();
                          const form = new FormData(event.currentTarget);
                          void save(
                            row,
                            {
                              readiness_status: form.get("readiness_status"),
                              resume_status: form.get("resume_status"),
                              mock_interview_status: form.get("mock_interview_status"),
                              aptitude_status: form.get("aptitude_status"),
                              available: form.get("available") === "on",
                              notes: form.get("notes"),
                            },
                            "Candidate profile updated."
                          );
                        }}
                      >
                        <div className="field">
                          <label htmlFor={`readiness-${row.student_id}`}>Readiness</label>
                          <input id={`readiness-${row.student_id}`} name="readiness_status" defaultValue={row.readiness_status} />
                        </div>
                        <div className="field">
                          <label htmlFor={`resume-${row.student_id}`}>Resume status</label>
                          <input id={`resume-${row.student_id}`} name="resume_status" defaultValue={row.resume_status} />
                        </div>
                        <div className="field">
                          <label htmlFor={`mock-${row.student_id}`}>Mock interview</label>
                          <input id={`mock-${row.student_id}`} name="mock_interview_status" defaultValue={row.mock_interview_status} />
                        </div>
                        <div className="field">
                          <label htmlFor={`aptitude-${row.student_id}`}>Aptitude</label>
                          <input id={`aptitude-${row.student_id}`} name="aptitude_status" defaultValue={row.aptitude_status} />
                        </div>
                        <div className="field">
                          <label htmlFor={`notes-${row.student_id}`}>Notes</label>
                          <textarea id={`notes-${row.student_id}`} name="notes" defaultValue={row.notes || ""} />
                        </div>
                        <div className="field"><label htmlFor={`available-${row.student_id}`}><input id={`available-${row.student_id}`} name="available" type="checkbox" defaultChecked={row.available} /> Available to employers</label></div>
                        <button className="btn small" disabled={busyId === row.student_id}>{busyId === row.student_id ? "Saving…" : "Save changes"}</button>
                      </form>
                    )}
                    {message?.id === row.student_id && (
                      <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 6, fontSize: 13 }}>
                        {message.text}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
