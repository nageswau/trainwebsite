"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type AgentRow = { id: string; name: string; email: string; approval_status: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  return "Unable to complete this action.";
}

// AGT-001: a Pending Agent could reach every agent-scoped endpoint immediately after
// self-registering, unapproved -- the approval gate existed in the data model but
// nothing enforced or actioned it. This is the real approve/reject action; the generic
// "Agent Registrations" table above only ever showed status as plain text.
export default function AgentApprovalPanel() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentRow[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function load() {
    fetch("/api/v1/overseas-admin/agents")
      .then((res) => (res.ok ? res.json() : []))
      .then(setAgents)
      .catch(() => setAgents([]));
  }

  useEffect(load, []);

  async function decide(agentId: string, action: "approve" | "reject") {
    setBusyId(agentId);
    setMessage(null);
    const response = await fetch(`/api/v1/overseas-admin/agents/${agentId}/${action}`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: agentId, text: detailMessage(data.detail), failed: true });
      return;
    }
    router.refresh();
    load();
  }

  if (agents === null) {
    return (
      <div className="action-card">
        <h3>Agent Approvals</h3>
        <p className="muted">Loading agent registrations…</p>
      </div>
    );
  }

  const pending = agents.filter((a) => a.approval_status === "pending");
  const decided = agents.filter((a) => a.approval_status !== "pending");

  return (
    <div className="action-card">
      <h3>Agent Approvals</h3>
      {pending.length === 0 ? (
        <p className="muted">No agent registrations awaiting approval.</p>
      ) : (
        <div className="grid two">
          {pending.map((agent) => (
            <div className="card" key={agent.id}>
              <span className="badge">Pending</span>
              <h4 style={{ marginTop: 10 }}>{agent.name}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{agent.email}</p>
              <button className="btn small" disabled={busyId === agent.id} onClick={() => decide(agent.id, "approve")} style={{ marginRight: 8 }}>
                {busyId === agent.id ? "Working…" : "Approve"}
              </button>
              <button className="btn secondary small" disabled={busyId === agent.id} onClick={() => decide(agent.id, "reject")}>
                Reject
              </button>
              {message?.id === agent.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {message.text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {decided.length > 0 && (
        <>
          <h4 style={{ marginTop: 24 }}>Decided</h4>
          <div className="grid two">
            {decided.map((agent) => (
              <div className="card" key={agent.id}>
                <span className="badge">{agent.approval_status}</span>
                <h4 style={{ marginTop: 10 }}>{agent.name}</h4>
                <p className="muted" style={{ fontSize: 13 }}>{agent.email}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
