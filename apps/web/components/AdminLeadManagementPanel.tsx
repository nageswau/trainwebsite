"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import AdminLeadFilters, { LEAD_FILTERS, type LeadFilter, type Organization } from "@/components/AdminLeadFilters";
import { LeadStageControl, LeadStageHistory } from "@/components/AdminLeadStage";
import BdmConfirm from "@/components/BdmConfirm";
import { sendJson, sendRequest, type Page } from "@/lib/apiErrors";
import { stageLabel } from "@/lib/leadStages";
import { pageOffset } from "@/lib/telecaller";
import { SOURCE_LABEL, getPage } from "@/lib/telecallerCatalogue";

type Ref = { id: string; full_name: string };
type AdminLeadRow = {
  id: string; name: string; email: string; phone: string | null; division: string; subject: string; status: string; source: string; crm_sync_status: string;
  // bdm-017: null for website / manual enquiries
  organization: Organization | null; bdm: Ref | null; converted_user: (Ref & { email: string }) | null;
  // tel-003 (spec §4): the lead record; each object is null when unset
  lead_code: string; priority: "hot" | "warm" | "cold"; product: { id: string; name: string } | null; campaign: { id: string; name: string } | null;
  telecaller: Ref | null; counselor: Ref | null;
};
type RowMessage = { id: string; text: string; failed: boolean };

const LEADS_URL = "/api/v1/admin/leads";
const PAGE_SIZE = 50;
const PRIORITY_LABEL = { hot: "Hot", warm: "Warm", cold: "Cold" };

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
// tel-003 (spec §5, T25): the API pages, filters and searches the list (no client-side cap); the filters, search and page live in the
// URL (tel-002 QA-04), so refresh keeps the place and Back returns to the previous view. Each row shows the Lead ID and lead fields.
// tel-004 (T25): the Status column is the pipeline stage with its history; "Change stage" offers only the valid moves.
export default function AdminLeadManagementPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = (params.get("q") ?? "").trim();
  const offset = pageOffset(params.get("offset") ?? undefined);
  const filters = Object.fromEntries(LEAD_FILTERS.map((key) => [key, params.get(key) ?? ""])) as Record<LeadFilter, string>;
  const request = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  if (query) request.set("q", query);
  request.set("limit", String(PAGE_SIZE));
  request.set("offset", String(offset));
  const requestUrl = `${LEADS_URL}?${request}`;
  const filtered = !!query || Object.values(filters).some(Boolean);

  const [data, setData] = useState<Page<AdminLeadRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [message, setMessage] = useState<RowMessage | null>(null);
  const seen = useRef(new Map<string, Organization>()); // the Organization filter's options: every organization shown so far

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    getPage<AdminLeadRow>(requestUrl, controller.signal)
      .then((page) => {
        for (const lead of page.items) if (lead.organization) seen.current.set(lead.organization.id, lead.organization);
        setData(page);
      })
      .catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  const organizations = [...seen.current.values()].sort((a, b) => a.code.localeCompare(b.code));

  /** A new filter or search starts again from the first page; only the pager passes an offset. */
  function go(changes: Record<string, string>, nextOffset = 0) {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    else next.delete("offset");
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  const replace = (next: AdminLeadRow) => setData((prev) => (prev ? { ...prev, items: prev.items.map((l) => (l.id === next.id ? next : l)) } : prev));

  return (
    <div className="action-card lead-management" aria-busy={data === null && !loadFailed}>
      <h3>Manage leads</h3>
      <AdminLeadFilters values={filters} query={query} organizations={organizations}
        onChange={(key, value) => go({ [key]: value })} onSearch={(text) => go({ q: text })} />
      {loadFailed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load leads.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading leads…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>{filtered ? "No leads match these filters." : "No leads found."}</p>
      ) : (
        <>
          <div className="table-scroll" style={{ marginTop: 12 }}> {/* QA17-03: the lead's name stays in view while the columns scroll */}
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Lead ID</th>
                  <th scope="col">Interest</th>
                  <th scope="col">Source · Campaign</th>
                  <th scope="col">Telecaller</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Organization</th>
                  <th scope="col">CRM sync</th>
                  <th scope="col">Status</th>
                  <th scope="col">Student</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">{row.name}</th>
                    <td style={{ whiteSpace: "nowrap" }}>{row.lead_code}</td>
                    <td>{row.product?.name ?? row.subject}</td>
                    <td>{SOURCE_LABEL[row.source] ?? row.source}{row.campaign && ` · ${row.campaign.name}`}</td>
                    <td>{row.telecaller ? row.telecaller.full_name : <span className="muted">Unassigned</span>}</td>
                    <td>{PRIORITY_LABEL[row.priority] ?? row.priority}</td>
                    <td>
                      {row.organization ? `${row.organization.code} · ${row.organization.name}` : "Website"}
                      {row.bdm && <div className="muted">by {row.bdm.full_name}</div>}
                    </td>
                    <td>{row.crm_sync_status === "failed" ? <span className="form-error">Failed</span> : row.crm_sync_status}</td>
                    <td>
                      {stageLabel(row.status)}
                      <LeadStageHistory key={row.status} lead={row} />
                    </td>
                    <td>
                      <LeadConversion row={row} onChanged={replace} onMessage={setMessage} />
                    </td>
                    <td>
                      <LeadStageControl lead={row} onMessage={setMessage} onChanged={(status) => replace({ ...row, status })} />
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
          {data.total > PAGE_SIZE && (
            <nav aria-label="Lead pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go({}, offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
