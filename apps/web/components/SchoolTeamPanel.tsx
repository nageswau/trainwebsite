"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Account = { id: string; name: string; email: string; role: string; active: boolean };
type Invite = { id: string; role: string; email: string; full_name: string; expires_at: string };

const ROLE_LABEL: Record<string, string> = {
  school_coordinator: "Coordinator",
  school_principal: "Principal",
  school_teacher: "Teacher",
  school_parent: "Parent",
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// SCH-003 (DEC-SCOPE-012): the Coordinator's team screen -- see who's already on board,
// invite Principal/Teacher/Parent accounts for the same institution. An invite is
// single-use and institution-scoped by construction (SCH-003-AC06) -- the Coordinator
// never chooses a school, it's always their own, server-derived.
export default function SchoolTeamPanel({ accounts, pendingInvites }: { accounts: Account[]; pendingInvites: Invite[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowMessage, setRowMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  // ENH010-QA-01: busyId alone doesn't guard against a 2nd/3rd click landing before the
  // first click's setBusyId re-render commits (all in the same tick) -- mirrors
  // ChangePasswordForm's `submitting` ref, but per-row since multiple accounts can toggle independently.
  const inFlight = useRef<Set<string>>(new Set());

  async function toggleActive(account: Account) {
    if (inFlight.current.has(account.id)) return;
    inFlight.current.add(account.id);
    setBusyId(account.id);
    setRowMessage(null);
    const response = await fetch(`/api/v1/school/team/accounts/${account.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !account.active }),
    });
    const data = await response.json().catch(() => ({}));
    inFlight.current.delete(account.id);
    setBusyId(null);
    if (!response.ok) {
      setRowMessage({ id: account.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    setRowMessage({ id: account.id, text: `${account.name} ${account.active ? "deactivated" : "reactivated"}.`, failed: false });
    router.refresh();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/school/team/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: form.get("role"), full_name: form.get("full_name"), email: form.get("email") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    const emailNote = data.email_status === "sent" ? "" : data.email_status === "not_configured" ? " (email sending isn't configured yet -- share the link manually)" : " (the email could not be sent -- share the link manually)";
    setMessage({ text: `Invite sent to ${data.email}${emailNote}. It's valid for 7 days.`, failed: false });
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Your team</h2>
        {/* The Coordinator always appears in their own roster (a valid, own-institution
            account like any other) -- "just you" means nobody else has joined yet, not
            literally zero rows. */}
        {accounts.filter((a) => a.role !== "school_coordinator").length === 0 ? (
          <p className="muted">It&apos;s just you so far. Invite your Principal, teachers, or parents to give them their own login.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Action</th></tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.email}</td>
                    <td>{ROLE_LABEL[a.role] || a.role}</td>
                    <td>{a.active ? "Active" : <span className="badge">Inactive</span>}</td>
                    <td>
                      {a.role === "school_coordinator" ? (
                        <span className="muted" style={{ fontSize: 13 }}>—</span>
                      ) : (
                        <>
                          <button className="btn small" disabled={busyId === a.id} onClick={() => toggleActive(a)}>
                            {busyId === a.id ? "Saving…" : a.active ? "Deactivate" : "Reactivate"}
                          </button>
                          {rowMessage?.id === a.id && (
                            <div className={rowMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 6, fontSize: 13 }}>
                              {rowMessage.text}
                            </div>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {pendingInvites.length > 0 && (
        <div className="card">
          <h2>Pending invites</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Email</th><th>Role</th><th>Expires</th></tr>
              </thead>
              <tbody>
                {pendingInvites.map((i) => (
                  <tr key={i.id}><td>{i.full_name}</td><td>{i.email}</td><td>{ROLE_LABEL[i.role] || i.role}</td><td>{new Date(i.expires_at).toLocaleDateString()}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="action-card">
        <h3>Invite a team member</h3>
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="invite-role">Role</label>
            <select id="invite-role" name="role" required defaultValue="">
              <option value="" disabled>Select role</option>
              <option value="school_principal">Principal</option>
              <option value="school_teacher">Teacher</option>
              <option value="school_parent">Parent</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="invite-name">Full name</label>
            <input id="invite-name" name="full_name" required />
          </div>
          <div className="field">
            <label htmlFor="invite-email">Email</label>
            <input id="invite-email" name="email" type="email" required />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Sending…" : "Send invite"}</button>
        </form>
        {message && (
          <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
}
