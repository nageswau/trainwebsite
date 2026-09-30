"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { detailMessage } from "@/lib/apiErrors";

type Master = { id: string; code: string; full_name: string; email: string; status: string; invite_pending: boolean; is_you: boolean };
type Team = { org: { id: string; name: string; prefix: string; status: string }; masters: Master[]; limit: number };

const TEAM_URL = "/api/v1/workflows/overseas/agent/team";
const NETWORK_ERROR = "Network error. Check your connection and try again.";
const FAILED = "Unable to complete this action.";

// AGN-001 (DEC-SCOPE-038 D4/D8/D9): an agency's Master accounts. Up to 3 active at once; invites use the
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
  // Browser QA-09: an announced confirmation after a deactivation (the badge change alone is silent to screen readers).
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef<Set<string>>(new Set());
  const inviteInFlight = useRef(false);
  // Keyboard support: Cancel returns focus to the Deactivate button that opened the confirmation.
  const returnFocusTo = useRef<string | null>(null);

  useEffect(() => {
    if (confirming === null && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [confirming]);

  function cancelConfirm(memberId: string) {
    returnFocusTo.current = `agent-team-deactivate-${memberId}`;
    setConfirming(null);
  }

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
    setNotice(null); // browser QA-08: a new action clears the previous one's message
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
        setInviteMessage({ text: detailMessage(data.detail, FAILED), failed: true });
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
    } catch {
      setInviteMessage({ text: NETWORK_ERROR, failed: true });
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
    setInviteMessage(null); // browser QA-08
    setNotice(null);
    try {
      const response = await fetch(`${TEAM_URL}/masters/${master.id}/deactivate`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setRowMessage({ id: master.id, text: detailMessage(data.detail, FAILED) });
        return;
      }
      setConfirming(null);
      if (master.is_you) {
        router.push("/overseas/login");
        return;
      }
      setNotice(`${master.code} ${master.full_name} deactivated.`);
      router.refresh();
      load();
    } catch {
      setRowMessage({ id: master.id, text: NETWORK_ERROR });
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
  // Browser QA-07: the server refuses self-deactivation until another active Master has accepted their invite (R3) --
  // say so up front instead of offering a confirmation that can only fail.
  const anotherAccepted = active.some((m) => !m.is_you && !m.invite_pending);

  return (
    <div className="action-card">
      <h3 style={{ overflowWrap: "anywhere" }}>Team — {team.org.name}</h3>
      {/* Always mounted so screen readers announce the text when it arrives; styled only while it has something to say. */}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
      <ul style={{ paddingLeft: 0, listStyle: "none" }}>
        {team.masters.map((m) => (
          <li className="card" key={m.id} style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
            <strong>{m.code}</strong> {m.full_name}{m.is_you ? " (you)" : ""} <span className="muted" style={{ fontSize: 13 }}>{m.email}</span>{" "}
            {m.status !== "active" ? <span className="badge">Deactivated</span> : m.invite_pending ? <span className="badge">Invite pending</span> : null}
            {m.status === "active" && active.length > 1 && m.is_you && !anotherAccepted && (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>You can deactivate your own account once another Master has accepted their invite.</p>
            )}
            {m.status === "active" && active.length > 1 && !(m.is_you && !anotherAccepted) && (
              confirming === m.id ? (
                <div role="group" aria-label={`Confirm deactivating ${m.full_name}`} style={{ marginTop: 8 }}>
                  <p style={{ fontSize: 13 }}>{m.is_you ? "Deactivate your own account? You will be signed out." : `Deactivate ${m.full_name}? They will no longer be able to sign in.`}</p>
                  <button className="btn small" autoFocus disabled={busyId === m.id} onClick={() => deactivate(m)} style={{ marginRight: 8 }}>
                    {busyId === m.id ? "Working…" : "Confirm deactivate"}
                  </button>
                  <button className="btn secondary small" disabled={busyId === m.id} onClick={() => cancelConfirm(m.id)}>Cancel</button>
                </div>
              ) : (
                <button id={`agent-team-deactivate-${m.id}`} className="btn secondary small" aria-label={`Deactivate ${m.full_name}${m.is_you ? " (you)" : ""}`} onClick={() => setConfirming(m.id)} style={{ marginLeft: 8 }}>
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
