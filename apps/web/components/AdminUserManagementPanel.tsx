"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { refocus } from "@/lib/focus";
import { type Feedback, errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

type Profile = { education?: string; skills?: string[]; [key: string]: unknown };
type AdminUserRow = { id: string; name: string; email: string; division: string; role: string; active: boolean; phone: string | null; profile: Profile; provisioning_status?: "active" | "pending_setup" | "link_expired" };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to update user.";
}

const SECTION_ROLES: Record<string, string[]> = {
  students: ["it_student", "overseas_student"],
  trainers: ["trainer"],
  counselors: ["counselor"],
};

// ADM-001: "Admin manages users, students, trainers." Create already existed; there was no
// way at all to deactivate/reactivate a user through the UI (only creation). Also wires up
// the new server-side guard (ADM-001-AC02): deactivating a trainer who still has
// active/upcoming batches assigned is blocked until explicitly confirmed here, rather than
// a silent flip that would strand those batches without a trainer.
//
// ADM-004: "views/edits directory detail records" -- this previously only offered a flat,
// unfiltered list with an activate/deactivate toggle, identical on `/it/admin/students` and
// `/it/admin/trainers` alike (the same list rendered on every one of those nav entries, not
// scoped to the section it was reached from). `section` now filters the directory to the
// relevant role, and "Edit details" opens the same full_name/phone/profile fields
// `PATCH /admin/users/{id}` already accepted -- ADM-004-AC02's field-level grant is enforced
// server-side by that endpoint's own explicit allowlist (role/division/email/password_hash
// were never PATCH-able through it), not reinvented here. Employer directory management
// (the third leg of this feature's own name) has no accounts to manage yet -- no `employer`
// role exists anywhere in this codebase until `EMP-001` (Employer registration) is built --
// so that section states this honestly rather than fabricating employer records.
export default function AdminUserManagementPanel({ section }: { section?: string } = {}) {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<({ id: string } & Feedback) | null>(null);
  const [setupFilter, setSetupFilter] = useState<"all" | "pending_setup" | "link_expired">("all");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/admin/users")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setUsers(data))
      .catch(() => !cancelled && setUsers([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const scopedRoles = section ? SECTION_ROLES[section] : undefined;

  const visible = useMemo(() => {
    if (!users) return [];
    const scoped = scopedRoles ? users.filter((u) => scopedRoles.includes(u.role)) : users;
    const bySetup = setupFilter === "all" ? scoped : scoped.filter((u) => u.provisioning_status === setupFilter);
    const normalized = query.trim().toLowerCase();
    if (!normalized) return bySetup;
    return bySetup.filter((u) => u.name.toLowerCase().includes(normalized) || u.email.toLowerCase().includes(normalized) || u.role.toLowerCase().includes(normalized));
  }, [users, query, scopedRoles, setupFilter]);

  async function toggleActive(row: AdminUserRow, confirmCascade: boolean) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/admin/users/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !row.active, ...(confirmCascade ? { confirm_cascade: true } : {}) }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      if (response.status === 409) {
        setConfirmingId(row.id);
        // A confirmation prompt, not a failure: amber, like the other "needs your attention" outcomes.
        setMessage({ id: row.id, text: `${detailMessage(data.detail)} Click "Confirm deactivate" to proceed anyway.`, tone: "warning" });
        return;
      }
      setMessage({ id: row.id, text: detailMessage(data.detail), tone: "error" });
      return;
    }
    setConfirmingId(null);
    setMessage({ id: row.id, text: `${row.name} ${row.active ? "deactivated" : "reactivated"}.`, tone: "success" });
    setUsers((prev) => (prev ? prev.map((u) => (u.id === row.id ? { ...u, active: !row.active } : u)) : prev));
    router.refresh();
  }

  // ENH-003: Re-send the set-password link to an account that has not set a password yet.
  async function resendWelcome(row: AdminUserRow) {
    setBusyId(row.id);
    setMessage(null);
    const { ok, data } = await requestWelcomeLink(row.id);
    setBusyId(null);
    if (!ok) {
      setMessage({ id: row.id, text: errorText(data.detail, "Unable to re-send the link."), tone: "error" });
    } else {
      setMessage({ id: row.id, ...welcomeLinkFeedback(`New link created for ${row.name}.`, data) });
      // The row is updated locally, so no server refresh here: a refresh re-renders the page and dropped keyboard
      // focus to <body> after the success message (QA-004). Nothing on this page reads the token state server-side.
      setUsers((prev) => (prev ? prev.map((u) => (u.id === row.id ? { ...u, provisioning_status: "pending_setup" } : u)) : prev));
    }
    refocus(`resend-${row.id}`);
  }

  async function saveDetails(row: AdminUserRow, form: FormData) {
    setBusyId(row.id);
    setMessage(null);
    const skills = String(form.get("skills") || "").split(",").map((value) => value.trim()).filter(Boolean);
    const response = await fetch(`/api/v1/admin/users/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: form.get("full_name"),
        phone: form.get("phone") || null,
        profile: { ...row.profile, education: form.get("education") || undefined, skills: skills.length ? skills : undefined },
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), tone: "error" });
      return;
    }
    setMessage({ id: row.id, text: "Details updated.", tone: "success" });
    setEditingId(null);
    setUsers((prev) =>
      prev
        ? prev.map((u) =>
            u.id === row.id
              ? { ...u, name: String(form.get("full_name") || u.name), phone: String(form.get("phone") || "") || null, profile: { ...u.profile, education: String(form.get("education") || ""), skills } }
              : u
          )
        : prev
    );
    router.refresh();
  }

  if (section === "employers") {
    return (
      <div className="action-card">
        <h3>Employers</h3>
        <p className="muted">No employer accounts exist yet -- employer self-registration (EMP-001) has not been built. This directory becomes available once employer accounts can be created.</p>
      </div>
    );
  }

  if (users === null) {
    return (
      <div className="action-card">
        <h3>{scopedRoles ? "Directory" : "Manage users"}</h3>
        <p className="muted">Loading users…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>{scopedRoles ? "Directory" : "Manage users"}</h3>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-user-search">Search by name, email, or role</label>
        <input id="admin-user-search" className="search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-user-setup">Account setup</label>
        <select id="admin-user-setup" value={setupFilter} onChange={(event) => setSetupFilter(event.target.value as "all" | "pending_setup" | "link_expired")}>
          <option value="all">All accounts</option>
          <option value="pending_setup">Awaiting setup</option>
          <option value="link_expired">Link expired</option>
        </select>
      </div>
      {users.length > 0 && (
        <p className="collection-summary" aria-live="polite" style={{ margin: "8px 0 0" }}>
          {visible.length} {visible.length === 1 ? "account" : "accounts"} shown
        </p>
      )}
      {visible.length === 0 ? (
        <div style={{ marginTop: 12 }}>
          <p className="muted">
            {users.length === 0
              ? "No users found."
              : setupFilter !== "all" && !query.trim()
                ? setupFilter === "pending_setup" ? "No accounts are awaiting setup." : "No accounts have an expired link."
                : "No records match this search."}
          </p>
          {setupFilter !== "all" && (
            <button type="button" className="btn ghost small" onClick={() => setSetupFilter("all")}>Show all accounts</button>
          )}
        </div>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }} role="region" aria-label={scopedRoles ? "Directory" : "Users"} tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.name}</th>
                  <td>{row.email}</td>
                  <td>{row.role}</td>
                  <td>
                    {row.active ? "Active" : "Inactive"}
                    {row.provisioning_status === "pending_setup" && <span className="status pending" style={{ marginLeft: 8 }}>Awaiting setup</span>}
                    {row.provisioning_status === "link_expired" && <span className="status error" style={{ marginLeft: 8 }}>Link expired</span>}
                  </td>
                  <td>
                    <button className="btn small" disabled={busyId === row.id} onClick={() => toggleActive(row, confirmingId === row.id)}>
                      {busyId === row.id ? "Saving…" : confirmingId === row.id ? "Confirm deactivate" : row.active ? "Deactivate" : "Reactivate"}
                    </button>{" "}
                    <button className="btn small secondary" disabled={busyId === row.id} onClick={() => setEditingId(editingId === row.id ? null : row.id)}>
                      {editingId === row.id ? "Cancel" : "Edit details"}
                    </button>
                    {row.active && (row.provisioning_status === "pending_setup" || row.provisioning_status === "link_expired") && (
                      <>
                        {" "}
                        <button
                          id={`resend-${row.id}`}
                          type="button"
                          className="btn small secondary"
                          disabled={busyId === row.id}
                          aria-label={`Re-send set-password link to ${row.name}`}
                          onClick={() => void resendWelcome(row)}
                        >
                          {busyId === row.id ? "Sending…" : "Re-send link"}
                        </button>
                      </>
                    )}
                    {editingId === row.id && (
                      <form
                        className="form"
                        style={{ marginTop: 10 }}
                        onSubmit={(event) => {
                          event.preventDefault();
                          void saveDetails(row, new FormData(event.currentTarget));
                        }}
                      >
                        <div className="field">
                          <label htmlFor={`directory-name-${row.id}`}>Full name</label>
                          <input id={`directory-name-${row.id}`} name="full_name" defaultValue={row.name} required />
                        </div>
                        <div className="field">
                          <label htmlFor={`directory-phone-${row.id}`}>Phone</label>
                          <input id={`directory-phone-${row.id}`} name="phone" defaultValue={row.phone || ""} />
                        </div>
                        <div className="field">
                          <label htmlFor={`directory-education-${row.id}`}>Education</label>
                          <input id={`directory-education-${row.id}`} name="education" defaultValue={String(row.profile?.education || "")} />
                        </div>
                        <div className="field">
                          <label htmlFor={`directory-skills-${row.id}`}>Skills (comma separated)</label>
                          <input id={`directory-skills-${row.id}`} name="skills" defaultValue={Array.isArray(row.profile?.skills) ? row.profile.skills.join(", ") : ""} />
                        </div>
                        <button className="btn small" disabled={busyId === row.id}>{busyId === row.id ? "Saving…" : "Save details"}</button>
                      </form>
                    )}
                    {message?.id === row.id && (
                      <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 6, fontSize: 13 }}>
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
