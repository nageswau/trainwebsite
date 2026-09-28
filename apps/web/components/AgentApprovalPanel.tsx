"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Master = { id: string; code: string; full_name: string; email: string; status: string };
type Org = { id: string; name: string; prefix: string; status: string; created_at: string; masters: Master[] };
type Action = "approve" | "reject" | "suspend" | "reinstate";

// AGN-001 (DEC-SCOPE-034 D6/D7): Overseas Admin acts on the agent ORGANISATION. Active organisations are labelled
// "Approved" -- the admin-facing word, and what agt-001-registration-approval.spec.ts looks for after approving.
const GROUPS: { status: string; label: string; empty: string; actions: Action[] }[] = [
  { status: "pending", label: "Pending", empty: "No organisations awaiting approval.", actions: ["approve", "reject"] },
  { status: "active", label: "Approved", empty: "No approved organisations.", actions: ["suspend"] },
  { status: "suspended", label: "Suspended", empty: "No suspended organisations.", actions: ["reinstate"] },
  { status: "rejected", label: "Rejected", empty: "No rejected organisations.", actions: ["approve"] },
];
const LABEL: Record<Action, string> = { approve: "Approve", reject: "Reject", suspend: "Suspend", reinstate: "Reinstate" };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  return "Unable to complete this action.";
}

export default function AgentApprovalPanel() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string } | null>(null);
  const inFlight = useRef<Set<string>>(new Set());
  // Keyboard support: Cancel returns focus to the Suspend button that opened the confirmation.
  const returnFocusTo = useRef<string | null>(null);

  useEffect(() => {
    if (confirming === null && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [confirming]);

  function cancelConfirm(orgId: string) {
    returnFocusTo.current = `agent-org-suspend-${orgId}`;
    setConfirming(null);
  }

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch("/api/v1/overseas-admin/agent-orgs")
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((rows: Org[]) => setOrgs(rows))
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  async function act(org: Org, action: Action) {
    if (inFlight.current.has(org.id)) return;
    inFlight.current.add(org.id);
    setBusyId(org.id);
    setMessage(null);
    try {
      const response = await fetch(`/api/v1/overseas-admin/agent-orgs/${org.id}/${action}`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage({ id: org.id, text: detailMessage(data.detail) });
        return;
      }
      setConfirming(null);
      router.refresh();
      load();
    } finally {
      inFlight.current.delete(org.id);
      setBusyId(null);
    }
  }

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Agent Approvals</h3>
        <p className="form-error" role="alert">Unable to load agent organisations.</p>
        <button className="btn secondary small" onClick={load}>Retry</button>
      </div>
    );
  }
  if (orgs === null) {
    return (
      <div className="action-card">
        <h3>Agent Approvals</h3>
        <p className="muted">Loading agent organisations…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Agent Approvals</h3>
      {GROUPS.map((group) => {
        const rows = orgs.filter((o) => o.status === group.status);
        const headingId = `agent-orgs-${group.status}`;
        return (
          <section key={group.status} aria-labelledby={headingId} style={{ marginTop: 16 }}>
            <h4 id={headingId}>{group.label}</h4>
            {rows.length === 0 ? (
              <p className="muted">{group.empty}</p>
            ) : (
              <div className="grid two">
                {rows.map((org) => (
                  <div className="card" key={org.id}>
                    <span className="badge">{group.label}</span>
                    <h5 style={{ marginTop: 10, fontSize: "1rem", overflowWrap: "anywhere" }}>{org.name} <span className="muted">({org.prefix})</span></h5>
                    <ul style={{ fontSize: 13, paddingLeft: 18, overflowWrap: "anywhere" }}>
                      {org.masters.map((m) => (
                        <li key={m.id}>
                          <span>{m.code} · {m.full_name}</span> <span className="muted">{m.email}{m.status !== "active" ? " (deactivated)" : ""}</span>
                        </li>
                      ))}
                    </ul>
                    {confirming === org.id ? (
                      <div role="group" aria-label="Confirm suspension">
                        <p style={{ fontSize: 13 }}>Suspend {org.name}? Every Master loses access on their next request.</p>
                        <button className="btn small" autoFocus disabled={busyId === org.id} onClick={() => act(org, "suspend")} style={{ marginRight: 8 }}>
                          {busyId === org.id ? "Working…" : "Confirm suspend"}
                        </button>
                        <button className="btn secondary small" disabled={busyId === org.id} onClick={() => cancelConfirm(org.id)}>Cancel</button>
                      </div>
                    ) : (
                      group.actions.map((action, i) => (
                        <button
                          key={action}
                          id={action === "suspend" ? `agent-org-suspend-${org.id}` : undefined}
                          className={i === 0 ? "btn small" : "btn secondary small"}
                          disabled={busyId === org.id}
                          onClick={() => (action === "suspend" ? setConfirming(org.id) : act(org, action))}
                          style={{ marginRight: 8 }}
                        >
                          {busyId === org.id ? "Working…" : LABEL[action]}
                        </button>
                      ))
                    )}
                    {message?.id === org.id && (
                      <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>{message.text}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
