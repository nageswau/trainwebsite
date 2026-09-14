"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Account = { id: string; name: string; email: string; role: string };
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
  return "Unable to send invite.";
}

// SCH-003 (DEC-SCOPE-012): the Coordinator's team screen -- see who's already on board,
// invite Principal/Teacher/Parent accounts for the same institution. An invite is
// single-use and institution-scoped by construction (SCH-003-AC06) -- the Coordinator
// never chooses a school, it's always their own, server-derived.
export default function SchoolTeamPanel({ accounts, pendingInvites }: { accounts: Account[]; pendingInvites: Invite[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

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
    setMessage({ text: `Invite sent to ${data.email}. It's valid for 7 days.`, failed: false });
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
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Role</th></tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}><td>{a.name}</td><td>{a.email}</td><td>{ROLE_LABEL[a.role] || a.role}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {pendingInvites.length > 0 && (
        <div className="card">
          <h2>Pending invites</h2>
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
