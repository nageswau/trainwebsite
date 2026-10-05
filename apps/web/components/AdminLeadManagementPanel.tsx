"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson, sendRequest } from "@/lib/apiErrors";

type Ref = { id: string; full_name: string };
type AdminLeadRow = {
  id: string; name: string; email: string; phone: string | null; division: string; subject: string; status: string; source: string; crm_sync_status: string;
  // bdm-017: null for website / manual enquiries
  organization: { id: string; code: string; name: string } | null; bdm: Ref | null; converted_user: (Ref & { email: string }) | null;
};
type RowMessage = { id: string; text: string; failed: boolean };

const STATUS_OPTIONS = ["new", "contacted", "qualified", "converted", "lost"];
const WEBSITE = "website"; // the Organization filter's value for unattributed leads

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update lead.";
}

const isRow = (data: unknown): data is AdminLeadRow => !!data && typeof (data as AdminLeadRow).id === "string" && "converted_user" in (data as object);

// bdm-017 (spec §6, AC3): the explicit link from a lead to one student account. The admin types the student's account email; the API
// matches it exactly and decides every rule. Unlinking asks first. Both answer with the updated row.
function LeadConversion({ row, onChanged, onMessage }: { row: AdminLeadRow; onChanged: (row: AdminLeadRow) => void; onMessage: (m: RowMessage) => void }) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(method: "POST" | "DELETE") {
    setBusy(true);
    const url = `/api/v1/admin/leads/${row.id}/conversion`;
    const outcome = method === "POST" ? await sendJson(url, "POST", { student_email: email.trim() }) : await sendRequest(url, { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isRow(outcome.data)) {
      setOpen(false);
      setEmail("");
      onChanged(outcome.data);
      onMessage({ id: row.id, text: method === "POST" ? "Student linked." : "Student unlinked.", failed: false });
    } else {
      onMessage({ id: row.id, text: outcome.ok ? "Unable to update lead." : outcome.message, failed: true });
    }
  }
  function link(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) return onMessage({ id: row.id, text: "Enter the student's account email.", failed: true });
    void send("POST");
  }

  if (row.converted_user) {
    return (
      <div>
        <div>{row.converted_user.full_name} ({row.converted_user.email})</div>
        {confirming ? (
          <BdmConfirm label="Confirm unlink" confirmText="Yes, unlink" busyText="Unlinking…" cancelText="Keep it" busy={busy}
            onConfirm={() => void send("DELETE")} onCancel={() => setConfirming(false)}>
            Unlink {row.converted_user.full_name} from this lead?
          </BdmConfirm>
        ) : (
          <button type="button" className="btn secondary small" aria-label={`Unlink student from ${row.name}`} onClick={() => setConfirming(true)}>Unlink</button>
        )}
      </div>
    );
  }
  if (!open) {
    return <button type="button" className="btn secondary small" aria-label={`Link student to ${row.name}`} onClick={() => setOpen(true)}>Link student</button>;
  }
  return (
    <form onSubmit={link} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      <input type="email" autoComplete="off" autoFocus aria-label={`Student account email for ${row.name}`} placeholder="student@example.com" value={email}
        onChange={(e) => setEmail(e.target.value)} disabled={busy} style={{ minWidth: 0, flex: "1 1 12rem" }} />
      <button type="submit" className="btn small" disabled={busy}>{busy ? "Linking…" : "Link"}</button>
      <button type="button" className="btn secondary small" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
    </form>
  );
}

// ADM-002: "Admin views/routes enquiry." The list and route (status update) endpoints
// already existed and already got ADM-002-AC02 right -- an enquiry stays visible and
// actionable no matter its crm_sync_status, so a failed Zoho sync never hides or blocks a
// real lead. This replaces the generic "type the lead's raw UUID" form with a picker that
// shows crm_sync_status directly, so a failed sync is visible at a glance rather than
// requiring the admin to already know which lead needs attention.
// bdm-017: each lead also shows the organization a BDM attributed it to (filterable), and the student account it converted to.
export default function AdminLeadManagementPanel() {
  const router = useRouter();
  const [leads, setLeads] = useState<AdminLeadRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [organization, setOrganization] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<RowMessage | null>(null);

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

  const organizations = useMemo(() => {
    const seen = new Map<string, NonNullable<AdminLeadRow["organization"]>>();
    for (const l of leads ?? []) if (l.organization) seen.set(l.organization.id, l.organization);
    return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
  }, [leads]);

  const visible = useMemo(() => {
    if (!leads) return [];
    const normalized = query.trim().toLowerCase();
    return leads.filter((l) => {
      if (organization === WEBSITE ? l.organization !== null : organization && l.organization?.id !== organization) return false;
      return !normalized || l.name.toLowerCase().includes(normalized) || l.email.toLowerCase().includes(normalized) || l.subject.toLowerCase().includes(normalized);
    });
  }, [leads, query, organization]);

  const replace = (next: AdminLeadRow) => setLeads((prev) => (prev ? prev.map((l) => (l.id === next.id ? next : l)) : prev));

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
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
        <div className="field" style={{ flex: "2 1 16rem" }}>
          <label htmlFor="admin-lead-search">Search by name, email, or subject</label>
          <input id="admin-lead-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="field" style={{ flex: "1 1 12rem" }}>
          <label htmlFor="admin-lead-organization">Organization</label>
          <select id="admin-lead-organization" value={organization} onChange={(event) => setOrganization(event.target.value)}>
            <option value="">All organizations</option>
            <option value={WEBSITE}>Website (no organization)</option>
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.code} · {o.name}
              </option>
            ))}
          </select>
        </div>
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
                <th scope="col">Organization</th>
                <th scope="col">CRM sync</th>
                <th scope="col">Status</th>
                <th scope="col">Student</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.name}</th>
                  <td>{row.subject}</td>
                  <td>
                    {row.organization ? `${row.organization.code} · ${row.organization.name}` : "Website"}
                    {row.bdm && <div className="muted">by {row.bdm.full_name}</div>}
                  </td>
                  <td>{row.crm_sync_status === "failed" ? <span className="form-error">Failed</span> : row.crm_sync_status}</td>
                  <td>{row.status}</td>
                  <td>
                    <LeadConversion row={row} onChanged={replace} onMessage={setMessage} />
                  </td>
                  <td>
                    <select aria-label={`${row.name} status`} value={row.status} onChange={(event) => void updateStatus(row, event.target.value)} disabled={busyId === row.id}>
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
