"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type AdminEnrollmentRow = { id: string; enrollment_code: string; student: string; email: string; batch: string; status: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update enrolment.";
}

// ADM-005: "Review a student's enrolment... and approve into active enrolment." Backs onto
// the new dedicated POST /admin/enrollments/{id}/approve and .../reject endpoints (the
// generic PATCH endpoint offered no "rejection is terminal" guarantee -- ADM-005-AC02 --
// so this always goes through the dedicated actions, never a raw status PATCH). No manual
// reference typing: pick the row, click the action.
export default function AdminEnrollmentReviewPanel() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminEnrollmentRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/admin/enrollments")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setRows(data))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    if (!rows) return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((r) => r.student.toLowerCase().includes(normalized) || r.email.toLowerCase().includes(normalized) || r.batch.toLowerCase().includes(normalized));
  }, [rows, query]);

  async function act(row: AdminEnrollmentRow, action: "approve" | "reject") {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/admin/enrollments/${row.id}/${action}`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: row.id, text: action === "approve" ? "Enrolment approved." : "Enrolment rejected.", failed: false });
    setRows((prev) => (prev ? prev.map((r) => (r.id === row.id ? { ...r, status: data.status } : r)) : prev));
    router.refresh();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Review enrolments</h3>
        <p className="muted">Loading enrolments…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Review enrolments</h3>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-enrollment-search">Search by student, email, or batch</label>
        <input id="admin-enrollment-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {visible.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{rows.length === 0 ? "No enrolments found." : "No enrolments match this search."}</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Student</th>
                <th scope="col">Batch</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.student}</th>
                  <td>{row.batch}</td>
                  <td>{row.status}</td>
                  <td>
                    {row.status === "rejected" ? (
                      <span className="muted" style={{ fontSize: 13 }}>Rejected -- final</span>
                    ) : (
                      <>
                        <button className="btn small" disabled={busyId === row.id || row.status === "active"} onClick={() => act(row, "approve")}>
                          {row.status === "active" ? "Approved" : busyId === row.id ? "Saving…" : "Approve"}
                        </button>{" "}
                        <button className="btn small secondary" disabled={busyId === row.id} onClick={() => act(row, "reject")}>
                          Reject
                        </button>
                      </>
                    )}
                    {message?.id === row.id && (
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
