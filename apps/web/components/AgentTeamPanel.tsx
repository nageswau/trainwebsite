"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Master = { id: string; code: string; full_name: string; email: string; status: string; invite_pending: boolean; is_you: boolean };
type Team = { org: { id: string; name: string; prefix: string; status: string }; masters: Master[]; limit: number };

const TEAM_URL = "/api/v1/workflows/overseas/agent/team";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// AGN-001 (DEC-SCOPE-034 D4/D8/D9): an agency's Master accounts. Up to 3 active at once; invites use the
// DEC-SCOPE-019 set-password email; the last active Master cannot be deactivated (server-enforced, 422 shown on a race).
export default function AgentTeamPanel() {
  const router = useRouter();
  const [team, setTeam] = useState<Team | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowMessage, setRowMessage] = useState<{ id: string; text: string } | null>(null);
  const inFlight = useRef<Set<string>>(new Set());
  const inviteInFlight = useRef(false);

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(TEAM_URL)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: Team) => setTeam(body))
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inviteInFlight.current) return;
    inviteInFlight.current = true;
    setInviting(true);
    setInviteMessage(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const response = await fetch(`${TEAM_URL}/masters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: form.get("full_name"), email: form.get("email"), phone: form.get("phone") || null }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setInviteMessage({ text: detailMessage(data.detail), failed: true });
        return;
      }
      formElement.reset();
      setInviteMessage(
        data.email_status === "sent"
          ? { text: "Invite sent.", failed: false }
          : { text: "Invite created, but the email was not delivered. Ask Overseas Admin to re-send the link.", failed: true },
      );
      router.refresh(); // the page's server-rendered Team table
      load();
    } finally {
      inviteInFlight.current = false;
      setInviting(false);
    }
  }

  async function deactivate(master: Master) {
    if (inFlight.current.has(master.id)) return;
    inFlight.current.add(master.id);
    setBusyId(master.id);
    setRowMessage(null);
    try {
      const response = await fetch(`${TEAM_URL}/masters/${master.id}/deactivate`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setRowMessage({ id: master.id, text: detailMessage(data.detail) });
        return;
      }
      setConfirming(null);
      if (master.is_you) {
        router.push("/overseas/login");
        return;
      }
      router.refresh();
      load();
    } finally {
      inFlight.current.delete(master.id);
      setBusyId(null);
    }
  }

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Team</h3>
        <p className="form-error" role="alert">Unable to load your team.</p>
        <button className="btn secondary small" onClick={load}>Retry</button>
      </div>
    );
  }
  if (team === null) {
    return (
      <div className="action-card">
        <h3>Team</h3>
        <p className="muted">Loading your team…</p>
      </div>
    );
  }

  const active = team.masters.filter((m) => m.status === "active");
  const atLimit = active.length >= team.limit;

  return (
    <div className="action-card">
      <h3 style={{ overflowWrap: "anywhere" }}>Team — {team.org.name}</h3>
      <ul style={{ paddingLeft: 0, listStyle: "none" }}>
        {team.masters.map((m) => (
          <li className="card" key={m.id} style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
            <strong>{m.code}</strong> {m.full_name}{m.is_you ? " (you)" : ""} <span className="muted" style={{ fontSize: 13 }}>{m.email}</span>{" "}
            {m.status !== "active" ? <span className="badge">Deactivated</span> : m.invite_pending ? <span className="badge">Invite pending</span> : null}
            {m.status === "active" && active.length > 1 && (
              confirming === m.id ? (
                <div role="group" aria-label={`Confirm deactivating ${m.full_name}`} style={{ marginTop: 8 }}>
                  <p style={{ fontSize: 13 }}>{m.is_you ? "Deactivate your own account? You will be signed out." : `Deactivate ${m.full_name}? They will no longer be able to sign in.`}</p>
                  <button className="btn small" disabled={busyId === m.id} onClick={() => deactivate(m)} style={{ marginRight: 8 }}>
                    {busyId === m.id ? "Working…" : "Confirm deactivate"}
                  </button>
                  <button className="btn secondary small" disabled={busyId === m.id} onClick={() => setConfirming(null)}>Cancel</button>
                </div>
              ) : (
                <button className="btn secondary small" aria-label={`Deactivate ${m.full_name}${m.is_you ? " (you)" : ""}`} onClick={() => setConfirming(m.id)} style={{ marginLeft: 8 }}>
                  Deactivate
                </button>
              )
            )}
            {rowMessage?.id === m.id && <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>{rowMessage.text}</div>}
          </li>
        ))}
      </ul>
      <form className="form" onSubmit={invite} aria-label="Invite a Master">
        <h4>Invite a Master</h4>
        {atLimit && <p className="muted">Limit reached: {team.limit} active Masters. Deactivate one to invite another.</p>}
        <div className="field"><label htmlFor="team-full-name">Full name</label><input id="team-full-name" name="full_name" maxLength={160} required disabled={atLimit} /></div>
        <div className="field"><label htmlFor="team-email">Email</label><input id="team-email" name="email" type="email" maxLength={320} required disabled={atLimit} /></div>
        <div className="field"><label htmlFor="team-phone">Phone (optional)</label><input id="team-phone" name="phone" type="tel" maxLength={40} disabled={atLimit} /></div>
        <button className="btn" disabled={atLimit || inviting}>{inviting ? "Sending…" : "Send invite"}</button>
        {inviteMessage && <div className={inviteMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>{inviteMessage.text}</div>}
      </form>
    </div>
  );
}
