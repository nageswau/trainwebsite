"use client";
import { useState } from "react";

import { ContactInputs, type ContactDraft, type ContactField } from "@/components/BdmContactFields";
import BdmConfirm from "@/components/BdmConfirm";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { CONTACT_ROLE_LABEL, type ContactRole, isOrganizationBody, MAX_CONTACTS, type OrgContact, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 (C1, C10; spec §6.2): an organization's contacts as blocks (not a table, so they read well on a phone). With edit rights a
// contact can be added, edited, made primary or deleted inline; the last one can't be deleted (C1). Every success re-renders from the
// organization the API returns. Contacts are data only: phones and emails are plain text (D29).
const FIELDS: ContactField[] = ["name", "designation", "role", "phone", "email"];

/** Browser QA-06: each value labelled, blanks left out (an unlabelled "— · — · — · email" line didn't say which was which). */
function details(c: OrgContact): string {
  const parts: [string, string | null][] = [
    ["Designation", c.designation],
    ["Role", c.role ? CONTACT_ROLE_LABEL[c.role as ContactRole] : null],
    ["Phone", c.phone],
    ["Email", c.email],
  ];
  const shown = parts.filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`);
  return shown.length ? shown.join(" · ") : "No other details";
}

const draftOf = (c?: OrgContact): ContactDraft => ({ name: c?.name ?? "", designation: c?.designation ?? "", role: c?.role ?? "", phone: c?.phone ?? "", email: c?.email ?? "" });

/** Add (no `initial`) or edit one contact. Sends only what changed on edit; blank values clear. */
function ContactEditor({ initial, busy, onSave, onCancel }: { initial?: OrgContact; busy: boolean; onSave: (body: Record<string, unknown>) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState(draftOf(initial));
  const [nameError, setNameError] = useState<string | null>(null);
  const save = () => {
    if (!draft.name.trim()) return setNameError("Contact name is required");
    const base = draftOf(initial);
    const body: Record<string, unknown> = {};
    for (const key of FIELDS) {
      const value = draft[key].trim();
      if (initial ? value !== base[key] : value) body[key] = value === "" ? null : value;
    }
    onSave(body);
  };
  return (
    <div className="form" role="group" aria-label={initial ? `Edit ${initial.name}` : "New contact"}>
      <ContactInputs
        idBase={`contact-${initial?.id ?? "new"}`}
        values={draft}
        errors={nameError ? { name: nameError } : {}}
        onChange={(field, value) => setDraft({ ...draft, [field]: value })}
        autoFocusName
      />
      <div className="actions">
        <button type="button" className="btn small" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save contact"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
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
  const addId = `org-${organization.id}-add-contact`;
  const editId = (contactId: string) => `contact-${contactId}-edit`;
  const deleteId = (contactId: string) => `contact-${contactId}-delete`;

  async function run(request: Promise<SendOutcome>, notice: string) {
    setBusy(true);
    setFailure(null);
    const outcome = await request;
    setBusy(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) {
      setEditing(null);
      setDeleting(null);
      focus(addId); // the control that had focus is gone (final review M5, spec F6)
      onChanged(outcome.data.organization, notice);
    } else setFailure(outcome.ok ? "Unable to update the contacts." : outcome.message);
  }
  // Every cancel returns focus to the control that opened the editor or the confirm (simplify review A5).
  const closeEditor = (returnTo: string) => {
    setEditing(null);
    focus(returnTo);
  };
  const cancelDelete = (contactId: string) => {
    setDeleting(null);
    focus(deleteId(contactId));
  };

  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-contacts`}>
      <h3 id={`org-${organization.id}-contacts`}>Contacts</h3>
      <ul aria-label="Contacts" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
        {organization.contacts.map((c) => (
          <li key={c.id} className="card" style={{ padding: 14 }}>
            {editing === c.id ? (
              <ContactEditor initial={c} busy={busy} onSave={(body) => void run(sendJson(`${url}/${c.id}`, "PATCH", body), "Contact updated.")} onCancel={() => closeEditor(editId(c.id))} />
            ) : (
              <>
                <p style={{ margin: 0, fontWeight: 800 }}>
                  {c.name} {c.is_primary && <span className="badge">Primary</span>}
                </p>
                <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>
                  {details(c)}
                </p>
                {canEdit && (
                  <div className="actions" style={{ marginTop: 8 }}>
                    <button id={editId(c.id)} type="button" className="btn secondary small" onClick={() => setEditing(c.id)} disabled={busy}>
                      Edit<span className="visually-hidden"> {c.name}</span>
                    </button>
                    {!c.is_primary && (
                      <button
                        type="button"
                        className="btn secondary small"
                        aria-label={`Make ${c.name} primary`}
                        onClick={() => void run(sendJson(`${url}/${c.id}`, "PATCH", { is_primary: true }), "Primary contact changed.")}
                        disabled={busy}
                      >
                        Make primary
                      </button>
                    )}
                    <button id={deleteId(c.id)} type="button" className="btn secondary small" onClick={() => setDeleting(c.id)} disabled={busy || last}>
                      Delete<span className="visually-hidden"> {c.name}</span>
                    </button>
                  </div>
                )}
                {deleting === c.id && (
                  <BdmConfirm
                    label="Confirm delete"
                    confirmText="Yes, delete"
                    busyText="Deleting…"
                    cancelText="Keep"
                    busy={busy}
                    onConfirm={() => void run(sendRequest(`${url}/${c.id}`, { method: "DELETE" }), "Contact deleted.")}
                    onCancel={() => cancelDelete(c.id)}
                  >
                    Delete {c.name}? This removes their details.
                  </BdmConfirm>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {canEdit && last && <p className="muted">An organization needs at least one contact.</p>}
      {canEdit &&
        (editing === "new" ? (
          <ContactEditor busy={busy} onSave={(body) => void run(sendJson(url, "POST", body), "Contact added.")} onCancel={() => closeEditor(addId)} />
        ) : (
          <div>
            <button id={addId} type="button" className="btn secondary small" onClick={() => setEditing("new")} disabled={busy || organization.contacts.length >= MAX_CONTACTS}>
              Add contact
            </button>
          </div>
        ))}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}
