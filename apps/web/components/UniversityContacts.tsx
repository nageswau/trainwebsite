"use client";
import { useRouter } from "next/navigation";
import { type ReactNode, useRef, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import {
  CONTACT_CHANNELS,
  type ContactRole,
  contactsUrl,
  contactUrl,
  label,
  MAX_CONTACTS,
  RELATIONSHIP_STRENGTHS,
  type UniversityContact,
} from "@/lib/universities";

// upc-006 (§10, §11): a university's contacts as blocks (they read well on a phone, like bdm-002's). With `canEdit` a contact can be
// added, edited, made primary or deleted inline; every success re-reads the page (router.refresh). Phones and emails are data only.
const TEXT = ["name", "designation", "department", "email", "phone", "whatsapp", "linkedin", "notes"] as const;
const CHOICE = ["role_code", "preferred_channel", "relationship_strength"] as const;
type Draft = Record<(typeof TEXT)[number] | (typeof CHOICE)[number], string> & { shareable: boolean; is_primary: boolean };

const draftOf = (c?: UniversityContact): Draft => ({
  name: c?.name ?? "", designation: c?.designation ?? "", department: c?.department ?? "", email: c?.email ?? "", phone: c?.phone ?? "",
  whatsapp: c?.whatsapp ?? "", linkedin: c?.linkedin ?? "", notes: c?.notes ?? "", role_code: c?.role?.code ?? "",
  preferred_channel: c?.preferred_channel ?? "", relationship_strength: c?.relationship_strength ?? "", shareable: c?.shareable ?? false, is_primary: false,
});

/** On create, what was filled in; on edit, only what changed (a cleared field is null). */
function bodyOf(draft: Draft, initial?: UniversityContact): Record<string, unknown> {
  const base = draftOf(initial);
  const body: Record<string, unknown> = {};
  for (const key of [...TEXT, ...CHOICE]) {
    const value = draft[key].trim();
    if (initial ? value !== base[key].trim() : value) body[key] = value || null;
  }
  if (initial ? draft.shareable !== base.shareable : draft.shareable) body.shareable = draft.shareable;
  if (!initial && draft.is_primary) body.is_primary = true;
  return body;
}

const SAVE_FAILED = "The change could not be saved. Try again.";
const LABELS: Record<string, string> = {
  name: "Name (required)", designation: "Designation", department: "Department", email: "Email", phone: "Phone", whatsapp: "WhatsApp",
  linkedin: "LinkedIn", notes: "Notes (internal)", role_code: "Role", preferred_channel: "Preferred communication", relationship_strength: "Relationship strength",
};
const LIMITS: Record<string, number> = { name: 200, designation: 120, department: 120, email: 255, phone: 30, whatsapp: 30, linkedin: 300, notes: 2000 };

function Field({ id, name, error, children }: { id: string; name: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{LABELS[name]}</label>
      {children}
      {error && <p className="field-error" id={`${id}-error`} style={{ color: "var(--red)", fontSize: 13, margin: "4px 0 0" }}>{error}</p>}
    </div>
  );
}

function ContactEditor({ initial, roles, offerPrimary, busy, errors, onSave, onCancel }: {
  initial?: UniversityContact; roles: ContactRole[]; offerPrimary: boolean; busy: boolean; errors: Record<string, string>;
  onSave: (body: Record<string, unknown>) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(() => draftOf(initial));
  const [nameError, setNameError] = useState<string | null>(null);
  const shown: Record<string, string> = nameError ? { ...errors, name: nameError } : errors;
  const id = (name: string) => `uc-${initial?.id ?? "new"}-${name}`;
  const a11y = (name: string) => (shown[name] ? { "aria-invalid": true as const, "aria-describedby": `${id(name)}-error` } : {});
  const set = (name: keyof Draft, value: string | boolean) => setDraft((d) => ({ ...d, [name]: value }));
  const choices: Record<(typeof CHOICE)[number], [string, string][]> = {
    role_code: roles.map((r) => [r.code, r.label]),
    preferred_channel: Object.entries(CONTACT_CHANNELS),
    relationship_strength: Object.entries(RELATIONSHIP_STRENGTHS),
  };
  const save = () => {
    if (!draft.name.trim()) return setNameError("Contact name is required");
    setNameError(null);
    onSave(bodyOf(draft, initial));
  };
  return (
    <div role="group" aria-label={initial ? `Edit ${initial.name}` : "New contact"} style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {TEXT.filter((n) => n !== "notes").map((name) => (
          <Field key={name} id={id(name)} name={name} error={shown[name]}>
            <input id={id(name)} value={draft[name]} maxLength={LIMITS[name]} autoFocus={name === "name"} onChange={(e) => set(name, e.target.value)}
              type={name === "email" ? "email" : name === "phone" || name === "whatsapp" ? "tel" : "text"}
              inputMode={name === "linkedin" ? "url" : undefined} placeholder={name === "linkedin" ? "linkedin.com/in/name" : undefined} {...a11y(name)} />
          </Field>
        ))}
        {CHOICE.map((name) => (
          <Field key={name} id={id(name)} name={name} error={shown[name]}>
            <select id={id(name)} value={draft[name]} onChange={(e) => set(name, e.target.value)} {...a11y(name)}>
              <option value="">Not set</option>
              {choices[name].map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </Field>
        ))}
      </div>
      <Field id={id("notes")} name="notes" error={shown.notes}>
        <textarea id={id("notes")} rows={2} maxLength={LIMITS.notes} value={draft.notes} onChange={(e) => set("notes", e.target.value)} {...a11y("notes")} />
      </Field>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={draft.shareable} onChange={(e) => set("shareable", e.target.checked)} /> Visible to counsellors (shareable)
        </label>
        {offerPrimary && (
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={draft.is_primary} onChange={(e) => set("is_primary", e.target.checked)} /> Make this the primary contact
          </label>
        )}
      </div>
      <div className="actions">
        <button type="button" className="btn small" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save contact"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  );
}

function ContactCard({ c }: { c: UniversityContact }) {
  const about = [c.designation, c.department, c.role?.label].filter(Boolean).join(" · ");
  const reach: ReactNode[] = [
    c.email && <a key="e" href={`mailto:${c.email}`}>{c.email}</a>,
    c.phone && <span key="p">Phone: {c.phone}</span>,
    c.whatsapp && <span key="w">WhatsApp: {c.whatsapp}</span>,
    c.linkedin && <a key="l" href={c.linkedin} target="_blank" rel="noopener noreferrer">{c.linkedin}</a>,
    c.preferred_channel && <span key="c">Prefers: {label(CONTACT_CHANNELS, c.preferred_channel)}</span>,
  ].filter(Boolean);
  return (
    <>
      <p style={{ margin: 0, fontWeight: 800, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {c.name}
        {c.is_primary && <span className="badge">Primary</span>}
        {c.relationship_strength && <span className="badge">{label(RELATIONSHIP_STRENGTHS, c.relationship_strength)}</span>}
        <span className="badge">{c.shareable ? "Shareable" : "Internal"}</span>
      </p>
      {about && <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>{about}</p>}
      {reach.length > 0 && (
        <p style={{ margin: 0, display: "flex", flexWrap: "wrap", columnGap: 12, overflowWrap: "anywhere" }}>{reach}</p>
      )}
      {c.notes && <p className="muted" style={{ margin: 0, whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{c.notes}</p>}
    </>
  );
}

export default function UniversityContacts({ universityId, contacts, roles, canEdit }: {
  universityId: string; contacts: UniversityContact[]; roles: ContactRole[]; canEdit: boolean;
}) {
  const router = useRouter();
  const sending = useRef(false);
  const [editing, setEditing] = useState<string | null>(null); // a contact id, "new", or null
  const [deleting, setDeleting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const addId = `uni-${universityId}-add-contact`;

  async function run(request: () => Promise<SendOutcome>, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    const outcome = await request();
    sending.current = false;
    setBusy(false);
    if (outcome.ok) {
      setEditing(null);
      setDeleting(null);
      setErrors({});
      setNotice(done);
      focus(addId); // the control that had focus is gone
      router.refresh();
      return;
    }
    const mapped = outcome.status === 422 ? fieldErrors(outcome.detail) : {};
    setErrors(mapped);
    // QA-I1: a response without a readable detail (e.g. a 500) gets a plain sentence; a dropped request keeps NOT_COMPLETED.
    const message = outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message;
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : message);
  }
  const open = (id: string | null) => {
    setEditing(id);
    setErrors({});
    setFailure(null);
  };

  return (
    <section className="action-card wide" aria-labelledby="uni-contacts">
      <h3 id="uni-contacts">Contacts</h3>
      {contacts.length === 0 && editing !== "new" && <p className="muted">No contacts recorded yet.</p>}
      {contacts.length > 0 && (
        <ul aria-label="Contacts" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {contacts.map((c) => (
            <li key={c.id} className="card" style={{ padding: 14, display: "grid", gap: 4 }}>
              {editing === c.id ? (
                <ContactEditor initial={c} roles={roles} offerPrimary={false} busy={busy} errors={errors}
                  onSave={(body) => void run(() => sendJson(contactUrl(c.id), "PATCH", body), "Contact updated.")} onCancel={() => open(null)} />
              ) : (
                <>
                  <ContactCard c={c} />
                  {canEdit && (
                    <div className="actions" style={{ marginTop: 8 }}>
                      <button type="button" className="btn secondary small" onClick={() => open(c.id)} disabled={busy}>
                        Edit<span className="visually-hidden"> {c.name}</span>
                      </button>
                      {!c.is_primary && (
                        <button type="button" className="btn secondary small" aria-label={`Make ${c.name} primary`} disabled={busy}
                          onClick={() => void run(() => sendJson(contactUrl(c.id), "PATCH", { is_primary: true }), "Primary contact changed.")}>
                          Make primary
                        </button>
                      )}
                      <button type="button" className="btn secondary small" onClick={() => setDeleting(c.id)} disabled={busy}>
                        Delete<span className="visually-hidden"> {c.name}</span>
                      </button>
                    </div>
                  )}
                  {deleting === c.id && (
                    <BdmConfirm label="Confirm delete" confirmText="Yes, delete" busyText="Deleting…" cancelText="Keep" busy={busy}
                      onConfirm={() => void run(() => sendRequest(contactUrl(c.id), { method: "DELETE" }), "Contact deleted.")}
                      onCancel={() => setDeleting(null)}>
                      Delete {c.name}? This removes their details.
                    </BdmConfirm>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (editing === "new" ? (
        <div className="card" style={{ padding: 14, marginTop: 12 }}>
          <ContactEditor roles={roles} offerPrimary={contacts.length > 0} busy={busy} errors={errors}
            onSave={(body) => void run(() => sendJson(contactsUrl(universityId), "POST", body), "Contact added.")} onCancel={() => open(null)} />
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button id={addId} type="button" className="btn secondary small" onClick={() => open("new")} disabled={busy || contacts.length >= MAX_CONTACTS}>
            Add contact
          </button>
          {contacts.length >= MAX_CONTACTS && <p className="muted">A university can have at most {MAX_CONTACTS} contacts.</p>}
        </div>
      ))}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}
