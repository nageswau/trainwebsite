"use client";
import { type KeyboardEvent, useState } from "react";

import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { CONTACT_ROLE_LABEL, CONTACT_ROLES, type ContactRole, display, isOrganizationBody, type OrgContact, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 (C1, C10; spec §6.2): an organization's contacts as blocks (not a table, so they read well on a phone). With edit rights a
// contact can be added, edited, made primary or deleted inline; the last one can't be deleted (C1). Every success re-renders from the
// organization the API returns. Contacts are data only: phones and emails are plain text (D29).
type Draft = { name: string; designation: string; role: string; phone: string; email: string };
const FIELDS = ["name", "designation", "role", "phone", "email"] as const;
const draftOf = (c?: OrgContact): Draft => ({ name: c?.name ?? "", designation: c?.designation ?? "", role: c?.role ?? "", phone: c?.phone ?? "", email: c?.email ?? "" });

function ContactEditor({ initial, busy, onSave, onCancel }: { initial?: OrgContact; busy: boolean; onSave: (body: Record<string, unknown>) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState(draftOf(initial));
  const [nameError, setNameError] = useState<string | null>(null);
  const base = draftOf(initial);
  const id = (field: string) => `contact-${initial?.id ?? "new"}-${field}`;
  const save = () => {
    if (!draft.name.trim()) return setNameError("Contact name is required");
    const body: Record<string, unknown> = {};
    for (const key of FIELDS) {
      const value = draft[key].trim();
      if (initial ? value !== base[key] : value) body[key] = value === "" ? null : value;
    }
    onSave(body);
  };
  const input = (field: "designation" | "phone" | "email", label: string, type = "text", max = 120) => (
    <div className="field">
      <label htmlFor={id(field)}>{label}</label>
      <input id={id(field)} type={type} maxLength={max} value={draft[field]} onChange={(e) => setDraft({ ...draft, [field]: e.target.value })} />
    </div>
  );
  return (
    <div className="form" role="group" aria-label={initial ? `Edit ${initial.name}` : "New contact"}>
      <div className="field">
        <label htmlFor={id("name")}>Contact name (required)</label>
        <input id={id("name")} autoFocus maxLength={200} value={draft.name} aria-required="true" aria-invalid={nameError ? true : undefined} aria-describedby={nameError ? id("name-error") : undefined} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        {nameError && <p className="form-error" id={id("name-error")}>{nameError}</p>}
      </div>
      {input("designation", "Designation")}
      <div className="field">
        <label htmlFor={id("role")}>Role</label>
        <select id={id("role")} value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
          <option value="">Not set</option>
          {CONTACT_ROLES.map((r) => <option key={r} value={r}>{CONTACT_ROLE_LABEL[r]}</option>)}
        </select>
      </div>
      {input("phone", "Phone", "tel", 30)}
      {input("email", "Email", "email", 255)}
      <div className="actions">
        <button type="button" className="btn small" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save contact"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  );
}

export default function BdmOrganizationContacts({ organization, onChanged }: { organization: Organization; onChanged: (o: Organization, notice: string) => void }) {
  const [editing, setEditing] = useState<string | null>(null); // a contact id, "new", or null
  const [deleting, setDeleting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const canEdit = organization.permissions.can_edit;
  const url = `${ORGS_URL}/${organization.id}/contacts`;
  const last = organization.contacts.length <= 1;

  async function run(request: Promise<SendOutcome>, notice: string) {
    setBusy(true);
    setFailure(null);
    const outcome = await request;
    setBusy(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) {
      setEditing(null);
      setDeleting(null);
      onChanged(outcome.data.organization, notice);
    } else setFailure(outcome.ok ? "Unable to update the contacts." : outcome.message);
  }
  const cancelDelete = (contactId: string) => {
    setDeleting(null);
    focus(`contact-${contactId}-delete`);
  };

  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-contacts`}>
      <h3 id={`org-${organization.id}-contacts`}>Contacts</h3>
      <ul aria-label="Contacts" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
        {organization.contacts.map((c) => (
          <li key={c.id} className="card" style={{ padding: 14 }}>
            {editing === c.id ? (
              <ContactEditor initial={c} busy={busy} onSave={(body) => void run(sendJson(`${url}/${c.id}`, "PATCH", body), "Contact updated.")} onCancel={() => setEditing(null)} />
            ) : (
              <>
                <p style={{ margin: 0, fontWeight: 800 }}>
                  {c.name} {c.is_primary && <span className="badge">Primary</span>}
                </p>
                <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>
                  {display(c.designation)} · {c.role ? CONTACT_ROLE_LABEL[c.role as ContactRole] : "—"} · {display(c.phone)} · {display(c.email)}
                </p>
                {canEdit && (
                  <div className="actions" style={{ marginTop: 8 }}>
                    <button type="button" className="btn secondary small" onClick={() => setEditing(c.id)} disabled={busy}>Edit<span className="visually-hidden"> {c.name}</span></button>
                    {!c.is_primary && (
                      <button type="button" className="btn secondary small" onClick={() => void run(sendJson(`${url}/${c.id}`, "PATCH", { is_primary: true }), "Primary contact changed.")} disabled={busy}>
                        Make<span className="visually-hidden"> {c.name}</span> primary
                      </button>
                    )}
                    <button id={`contact-${c.id}-delete`} type="button" className="btn secondary small" onClick={() => setDeleting(c.id)} disabled={busy || last}>
                      Delete<span className="visually-hidden"> {c.name}</span>
                    </button>
                  </div>
                )}
                {deleting === c.id && (
                  <div role="group" aria-label="Confirm delete" onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && cancelDelete(c.id)}>
                    <p>Delete {c.name}? This removes their details.</p>
                    <button type="button" className="btn small" autoFocus onClick={() => void run(sendRequest(`${url}/${c.id}`, { method: "DELETE" }), "Contact deleted.")} disabled={busy}>{busy ? "Deleting…" : "Yes, delete"}</button>{" "}
                    <button type="button" className="btn secondary small" onClick={() => cancelDelete(c.id)}>Keep</button>
                  </div>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {canEdit && last && <p className="muted">An organization needs at least one contact.</p>}
      {canEdit &&
        (editing === "new" ? (
          <ContactEditor busy={busy} onSave={(body) => void run(sendJson(url, "POST", body), "Contact added.")} onCancel={() => setEditing(null)} />
        ) : (
          <div>
            <button type="button" className="btn secondary small" onClick={() => setEditing("new")} disabled={busy || organization.contacts.length >= 20}>Add contact</button>
          </div>
        ))}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </section>
  );
}
