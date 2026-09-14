"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type AdminLeadRow = { id: string; name: string; email: string; phone: string | null; division: string; subject: string; status: string; source: string; crm_sync_status: string };

const STATUS_OPTIONS = ["new", "contacted", "qualified", "converted", "lost"];

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update lead.";
}

// ADM-002: "Admin views/routes enquiry." The list and route (status update) endpoints
// already existed and already got ADM-002-AC02 right -- an enquiry stays visible and
// actionable no matter its crm_sync_status, so a failed Zoho sync never hides or blocks a
// real lead. This replaces the generic "type the lead's raw UUID" form with a picker that
// shows crm_sync_status directly, so a failed sync is visible at a glance rather than
// requiring the admin to already know which lead needs attention.
export default function AdminLeadManagementPanel() {
  const router = useRouter();
  const [leads, setLeads] = useState<AdminLeadRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/admin/leads")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setLeads(data))
      .catch(() => !cancelled && setLeads([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    if (!leads) return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return leads;
    return leads.filter((l) => l.name.toLowerCase().includes(normalized) || l.email.toLowerCase().includes(normalized) || l.subject.toLowerCase().includes(normalized));
  }, [leads, query]);

  async function updateStatus(row: AdminLeadRow, status: string) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/admin/leads/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: row.id, text: "Lead updated.", failed: false });
    setLeads((prev) => (prev ? prev.map((l) => (l.id === row.id ? { ...l, status } : l)) : prev));
    router.refresh();
  }

  if (leads === null) {
    return (
      <div className="action-card">
        <h3>Manage leads</h3>
        <p className="muted">Loading leads…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Manage leads</h3>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-lead-search">Search by name, email, or subject</label>
        <input id="admin-lead-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {visible.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{leads.length === 0 ? "No leads found." : "No leads match this search."}</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Subject</th>
                <th scope="col">CRM sync</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.name}</th>
                  <td>{row.subject}</td>
                  <td>{row.crm_sync_status === "failed" ? <span className="form-error">Failed</span> : row.crm_sync_status}</td>
                  <td>{row.status}</td>
                  <td>
                    <select aria-label={`${row.name} status`} defaultValue={row.status} onChange={(event) => void updateStatus(row, event.target.value)} disabled={busyId === row.id}>
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
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
