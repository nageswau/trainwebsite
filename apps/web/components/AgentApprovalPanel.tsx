"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Master = { id: string; code: string; full_name: string; email: string; status: string };
type Org = { id: string; name: string; prefix: string; status: string; created_at: string; masters: Master[] };
type Page = { items: Org[]; total: number; limit: number; offset: number };
type Status = "pending" | "active" | "suspended" | "rejected";
type Action = "approve" | "reject" | "suspend" | "reinstate";

// AGN-001 (DEC-SCOPE-034 D6/D7): Overseas Admin acts on the agent ORGANISATION, one status tab at a time, 20 per page
// (the list is paginated server-side). Active organisations are labelled "Approved" -- the admin-facing word, and what
// agt-001-registration-approval.spec.ts looks for after approving.
const TABS: { status: Status; label: string; empty: string; actions: Action[] }[] = [
  { status: "pending", label: "Pending", empty: "No organisations awaiting approval.", actions: ["approve", "reject"] },
  { status: "active", label: "Approved", empty: "No approved organisations.", actions: ["suspend"] },
  { status: "suspended", label: "Suspended", empty: "No suspended organisations.", actions: ["reinstate"] },
  { status: "rejected", label: "Rejected", empty: "No rejected organisations.", actions: ["approve"] },
];
const LABEL: Record<Action, string> = { approve: "Approve", reject: "Reject", suspend: "Suspend", reinstate: "Reinstate" };
// After an action the panel follows the organisation to its new tab, so the admin sees the result.
const RESULT: Record<Action, Status> = { approve: "active", reject: "rejected", suspend: "suspended", reinstate: "active" };
const PAGE_SIZE = 20;
const LIST_URL = "/api/v1/overseas-admin/agent-orgs";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  return "Unable to complete this action.";
}

export default function AgentApprovalPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("pending");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string } | null>(null);
  const inFlight = useRef<Set<string>>(new Set());
  // Keyboard support: Cancel returns focus to the Suspend button that opened the confirmation.
  const returnFocusTo = useRef<string | null>(null);

  const load = useCallback(() => {
    setLoadFailed(false);
    setData(null);
    fetch(`${LIST_URL}?status=${status}&limit=${PAGE_SIZE}&offset=${offset}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: Page) => setData(body))
      .catch(() => setLoadFailed(true));
  }, [status, offset]);

  useEffect(load, [load]);

  useEffect(() => {
    if (confirming === null && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [confirming]);

  function showTab(next: Status) {
    setConfirming(null);
    setMessage(null);
    setStatus(next);
    setOffset(0);
  }

  function cancelConfirm(orgId: string) {
    returnFocusTo.current = `agent-org-suspend-${orgId}`;
    setConfirming(null);
  }

  async function act(org: Org, action: Action) {
    if (inFlight.current.has(org.id)) return;
    inFlight.current.add(org.id);
    setBusyId(org.id);
    setMessage(null);
    try {
      const response = await fetch(`${LIST_URL}/${org.id}/${action}`, { method: "POST" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage({ id: org.id, text: detailMessage(body.detail) });
        return;
      }
      router.refresh();
      if (RESULT[action] === status) load();
      else showTab(RESULT[action]);
      setConfirming(null);
    } finally {
      inFlight.current.delete(org.id);
      setBusyId(null);
    }
  }

  const tab = TABS.find((t) => t.status === status) ?? TABS[0];

  return (
    <div className="action-card">
      <h3>Agent Approvals</h3>
      <div role="group" aria-label="Organisation status" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {TABS.map((t) => (
          <button key={t.status} type="button" className={t.status === status ? "btn small" : "btn secondary small"} aria-pressed={t.status === status} onClick={() => showTab(t.status)}>
            {t.label}
          </button>
        ))}
      </div>
      <section aria-labelledby="agent-orgs-heading" style={{ marginTop: 16 }}>
        <h4 id="agent-orgs-heading">{tab.label}</h4>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load agent organisations.</p>
            <button className="btn secondary small" onClick={load}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted">Loading agent organisations…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">{tab.empty}</p>
        ) : (
          <>
            <div className="grid two">
              {data.items.map((org) => (
                <div className="card" key={org.id}>
                  <span className="badge">{tab.label}</span>
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
                    tab.actions.map((action, i) => (
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
            <nav aria-label="Organisation pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          </>
        )}
      </section>
    </div>
  );
}
