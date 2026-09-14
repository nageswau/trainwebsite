"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type TicketRow = {
  id: string;
  subject: string;
  description: string;
  priority: string;
  status: string;
  division: string;
  assigned_to_user_id: string | null;
  resolution_note: string | null;
  created_at: string;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update the ticket.";
}

// STU-005: Trainer/Admin resolve queue. An unassigned ticket stays visible in this list,
// never hidden (STU-005-AC02) -- the server auto-claims it to whichever staff member
// acts on it first, so there's no separate "assign to X" picker to build.
export default function SupportTicketQueuePanel() {
  const router = useRouter();
  const [rows, setRows] = useState<TicketRow[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/workflows/support")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setRows(data))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function act(row: TicketRow, status: "in_progress" | "resolved") {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/support/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, resolution_note: notes[row.id] || undefined }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: row.id, text: status === "resolved" ? "Ticket resolved." : "Ticket marked in progress.", failed: false });
    setRows((prev) => (prev ? prev.map((r) => (r.id === row.id ? { ...r, status: data.status, assigned_to_user_id: data.assigned_to_user_id, resolution_note: data.resolution_note } : r)) : prev));
    router.refresh();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Support tickets</h3>
        <p className="muted">Loading tickets…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Support tickets</h3>
      {rows.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>No support tickets right now.</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Subject</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Assigned</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">
                    {row.subject}
                    <br />
                    <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{row.description}</span>
                  </th>
                  <td>{row.priority}</td>
                  <td>{row.status}</td>
                  <td>{row.assigned_to_user_id ? "Assigned" : <span className="badge">Unassigned</span>}</td>
                  <td>
                    {row.status === "resolved" || row.status === "closed" ? (
                      <span className="muted" style={{ fontSize: 13 }}>{row.status === "resolved" ? "Resolved" : "Closed"}{row.resolution_note ? ` — ${row.resolution_note}` : ""}</span>
                    ) : (
                      <>
                        <div className="field">
                          <label htmlFor={`ticket-note-${row.id}`}>Resolution note</label>
                          <textarea id={`ticket-note-${row.id}`} value={notes[row.id] || ""} onChange={(event) => setNotes((prev) => ({ ...prev, [row.id]: event.target.value }))} />
                        </div>
                        <button className="btn small" disabled={busyId === row.id} onClick={() => act(row, "in_progress")}>
                          {busyId === row.id ? "Saving…" : "Mark in progress"}
                        </button>{" "}
                        <button className="btn small secondary" disabled={busyId === row.id} onClick={() => act(row, "resolved")}>
                          Resolve
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
