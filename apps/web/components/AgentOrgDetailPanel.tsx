"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import AgentNetworkRecords from "@/components/AgentNetworkRecords";
import { formatInr } from "@/lib/agentApplications";
import { failureText, NETWORK_ERROR, NETWORK_PATH, ORG_STATUS_LABEL, orgUrl, statusClass, type CommissionTotal, type OrgDetail } from "@/lib/agentNetwork";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-022 (DEC-SCOPE-063): one agency for Overseas and Super Admins -- its figures, money and Masters; its students and
// applications on request (each page is an audited read, N2); and, for Overseas Admin only (N3), suspend / reinstate through the
// AGN-001 action, which denies every member on their next request. Approve / reject stay on Agent Approvals (N6).
type Action = "suspend" | "reinstate";
type Records = "students" | "applications";
const APPROVALS_PATH = "/overseas/admin/agents";
const DONE: Record<Action, string> = { suspend: "suspended", reinstate: "reinstated" };

// Commission keeps its own currency on every row: amounts in different currencies are never added together (N4).
function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

export default function AgentOrgDetailPanel({ orgId, canAct }: { orgId: string; canAct: boolean }) {
  const [org, setOrg] = useState<OrgDetail | null>(null);
  const [loadError, setLoadError] = useState<{ text: string; missing: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [records, setRecords] = useState<Records | null>(null);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await fetch(orgUrl(orgId));
      if (!res.ok) {
        setLoadError({ text: await failureText(res, "Unable to load this agency."), missing: res.status === 404 });
        return;
      }
      setOrg((await res.json()) as OrgDetail);
    } catch {
      setLoadError({ text: NETWORK_ERROR, missing: false });
    }
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load, retry]);

  async function act(action: Action) {
    if (!org || inFlight.current) return; // one request, however many clicks
    inFlight.current = true;
    setBusy(true);
    setNotice(null);
    setActionError(null);
    try {
      const res = await fetch(`${orgUrl(orgId)}/${action}`, { method: "POST" });
      if (res.ok) setNotice(`${org.name} ${DONE[action]}.`);
      else setActionError(await failureText(res, `Unable to ${action} this agency.`));
      setConfirming(false);
      await load(); // a 409 means someone else moved it: show where it is now
      // After the reload, so the button for the new state exists; whichever is rendered gets focus.
      focus("agent-org-reinstate", "agent-org-suspend");
    } catch {
      setActionError(NETWORK_ERROR);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const back = (
    <Link href={NETWORK_PATH} className="muted" style={{ fontSize: 13 }}>
      ← Agent network
    </Link>
  );

  if (loadError && !org) {
    return (
      <div className="action-card">
        {back}
        <p className="form-error" role="alert">
          {loadError.text}
        </p>
        {!loadError.missing && (
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>
            Retry
          </button>
        )}
      </div>
    );
  }
  if (!org) {
    return (
      <div className="action-card">
        {back}
        <p className="muted" role="status">
          Loading agency…
        </p>
      </div>
    );
  }

  const figures: [string, number][] = [
    ["Staff", org.staff_count],
    ["Students", org.counts.students],
    ["Applications", org.counts.applications],
    ["Enrollments", org.counts.enrollments],
  ];

  return (
    <div className="action-card agent-network">
      <div>
        {back}
        <h2 style={{ overflowWrap: "anywhere", marginTop: 8 }}>
          {org.name} <span className="muted">({org.prefix})</span>
        </h2>
        <p>
          <span className={statusClass(org.status)}>{ORG_STATUS_LABEL[org.status] ?? org.status}</span>{" "}
          <span className="muted" style={{ fontSize: 13 }}>
            since {formatDate(org.status_changed_at ?? org.created_at)}
          </span>
        </p>
        {/* Always mounted so screen readers announce the result when it arrives; inside the header so that, while empty, it adds
            no gap of its own to the card's grid (QA22-10). */}
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite">
          {notice}
        </div>
      </div>
      {/* A refresh that failed after the first load: the figures below may be out of date, so say so (final review). */}
      {loadError && (
        <div>
          <p className="form-error" role="alert">
            {loadError.text} The figures below may be out of date.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>
            Retry
          </button>
        </div>
      )}
      {canAct && (
        <div>
          {org.status === "active" &&
            (confirming ? (
              <div
                role="group"
                aria-label="Confirm suspension"
                onKeyDown={(e) => {
                  if (e.key === "Escape" && !busy) {
                    setConfirming(false); // QA22-08: Escape cancels, like the Cancel button
                    focus("agent-org-suspend");
                  }
                }}
              >
                <p style={{ fontSize: 13 }}>Suspend {org.name}? Every member loses access on their next request.</p>
                <button type="button" className="btn small" autoFocus disabled={busy} onClick={() => act("suspend")} style={{ marginRight: 8 }}>
                  {busy ? "Working…" : "Confirm suspend"}
                </button>
                <button
                  type="button"
                  className="btn secondary small"
                  disabled={busy}
                  onClick={() => {
                    setConfirming(false);
                    focus("agent-org-suspend");
                  }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button id="agent-org-suspend" type="button" className="btn small" aria-label={`Suspend ${org.name}`} onClick={() => setConfirming(true)}>
                Suspend
              </button>
            ))}
          {org.status === "suspended" && (
            <button id="agent-org-reinstate" type="button" className="btn small" aria-label={`Reinstate ${org.name}`} disabled={busy} onClick={() => act("reinstate")}>
              {busy ? "Working…" : "Reinstate"}
            </button>
          )}
          {(org.status === "pending" || org.status === "rejected") && <Link href={APPROVALS_PATH}>Review in Agent Approvals</Link>}
          {actionError && (
            <p className="form-error" role="alert" style={{ marginTop: 8, fontSize: 13 }}>
              {actionError}
            </p>
          )}
        </div>
      )}

      <ul className="metric-grid" aria-label="Agency figures" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {figures.map(([label, value]) => (
          <li className="metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </li>
        ))}
      </ul>

      <section className="kpi-group">
        <h3 id="agent-org-commission">Commission</h3>
        <div className="table-scroll">
          {/* QA22-02: four columns do not fit a phone; `stack` turns each row into a labelled block there (data-label). */}
          <table className="table compact stack" aria-labelledby="agent-org-commission">
            <thead>
              <tr>
                <th scope="col">Figure</th>
                <th scope="col">Currency</th>
                <th scope="col">Count</th>
                <th scope="col">Amount</th>
              </tr>
            </thead>
            <tbody>
              <MoneyRows label="Claimable" rows={org.commission.claimable} />
              <tr>
                <th scope="row">Claims</th>
                <td data-label="Currency">—</td>
                <td data-label="Count">{org.commission.claims}</td>
                <td data-label="Amount">—</td>
              </tr>
              <MoneyRows label="Paid revenue" rows={org.commission.revenue} />
            </tbody>
          </table>
        </div>
      </section>

      <section className="kpi-group">
        <h3 id="agent-org-deposits">Deposits</h3>
        <div className="table-scroll">
          <table className="table compact" aria-labelledby="agent-org-deposits">
            <tbody>
              <tr>
                <th scope="row">Collected ({org.deposits.count})</th>
                <td>{formatInr(String(org.deposits.collected))}</td>
              </tr>
              <tr>
                <th scope="row">Remitted to universities</th>
                <td>{formatInr(String(org.deposits.remitted))}</td>
              </tr>
              <tr>
                <th scope="row">Refunded</th>
                <td>{formatInr(String(org.deposits.refunded))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="kpi-group">
        <h3>Masters</h3>
        <ul style={{ fontSize: 13, paddingLeft: 18, overflowWrap: "anywhere" }}>
          {org.masters.map((m) => (
            <li key={m.id}>
              {m.code} · {m.full_name} <span className="muted">{m.email}{m.status !== "active" ? " (deactivated)" : ""}</span>
            </li>
          ))}
        </ul>
      </section>

      <div role="group" aria-label="Agency records" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {(["students", "applications"] as const).map((r) => (
          <button key={r} type="button" className={records === r ? "btn small" : "btn secondary small"} aria-pressed={records === r} onClick={() => setRecords(r)}>
            {r === "students" ? "Students" : "Applications"}
          </button>
        ))}
      </div>
      {records && <AgentNetworkRecords key={records} orgId={orgId} kind={records} />}
    </div>
  );
}

function MoneyRows({ label, rows }: { label: string; rows: CommissionTotal[] }) {
  if (rows.length === 0) {
    return (
      <tr>
        <th scope="row">{label}</th>
        <td data-label="Currency">—</td>
        <td data-label="Count">0</td>
        <td data-label="Amount">—</td>
      </tr>
    );
  }
  return (
    <>
      {rows.map((r) => (
        <tr key={`${label}-${r.currency}`}>
          <th scope="row">{label}</th>
          <td data-label="Currency">{r.currency}</td>
          <td data-label="Count">{r.count}</td>
          <td data-label="Amount">{money(r.amount, r.currency)}</td>
        </tr>
      ))}
    </>
  );
}
