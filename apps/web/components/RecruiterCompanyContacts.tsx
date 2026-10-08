"use client";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import RecruiterContactFields from "@/components/RecruiterContactFields";
import { sendJson } from "@/lib/apiErrors";
import { display } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { telHref } from "@/lib/recruiterCalls";
import { safeLink } from "@/lib/recruiterCompanies";
import {
  businessContacts,
  CHANNEL_LABEL,
  type Contact,
  CONTACT_FIELDS,
  contactBody,
  contactErrorsOf,
  type ContactErrors,
  type ContactList,
  contactsOf,
  CONTACTS_URL,
  contactValuesOf,
  isContactList,
} from "@/lib/recruiterContacts";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-004 (spec §4; EVID-018 §3-§4): a company's contacts. The §3 Business Details are read from the contacts (C5); the list is cards (not
// a table) so it reads well on a phone. With `can_edit` a contact can be added, edited, made primary, deactivated (confirmed first) or
// reactivated; every success re-renders from the list the API returns. The mobile is a `tel:` link (rec-025); emails stay plain text until rec-026.
const MAX_CONTACTS = 50;
const names = (list: Contact[]) => (list.length ? list.map((c) => c.name).join(", ") : "—");

function details(c: Contact): [string, ReactNode][] {
  const link = safeLink(c.linkedin_url);
  const tel = telHref(c.mobile);
  const rows: [string, ReactNode][] = [
    ["Designation", c.designation],
    ["Department", c.department],
    ["Role", c.role ? `${c.role.name}${c.role.active ? "" : " (inactive)"}` : null],
    ["Mobile", tel ? <a href={tel}>{c.mobile}<span className="visually-hidden"> (call {c.name})</span></a> : c.mobile], // rec-025
    ["Email", c.email],
    [
      "LinkedIn",
      link && (
        <a href={link} target="_blank" rel="noopener noreferrer">
          {link}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      ),
    ],
    ["Preferred communication", c.preferred_channel && CHANNEL_LABEL[c.preferred_channel]],
    ["Last contacted", c.last_contacted_at ? <LocalTime value={c.last_contacted_at} time /> : "Not yet"],
    ["Next follow-up", c.next_follow_up_at ? formatSchoolDateTime(c.next_follow_up_at, true) : "None scheduled"], // rec-024 FU9
    ["Notes", c.notes && multiline(c.notes)],
  ];
  return rows.filter(([, value]) => value);
}

/** Add (no `initial`) or edit one contact. Edit sends only what changed; blank clears. Field errors from the server land on their field. */
function ContactEditor({ initial, roles, busy, onSave, onCancel }: { initial?: Contact; roles: CatalogueValue[]; busy: boolean; onSave: (body: Record<string, unknown>) => Promise<ContactErrors | null>; onCancel: () => void }) {
  const [values, setValues] = useState(contactValuesOf(initial));
  const [errors, setErrors] = useState<ContactErrors>({});
  const idPrefix = `contact-${initial?.id ?? "new"}`;
  async function save() {
    if (!values.name.trim()) return setErrors({ name: "Contact name is required" });
    const found = await onSave(contactBody(values, initial ? contactValuesOf(initial) : undefined));
    if (found) setErrors(found);
  }
  return (
    <div className="form" role="group" aria-label={initial ? `Edit ${initial.name}` : "New contact"}>
      <RecruiterContactFields idPrefix={idPrefix} fields={CONTACT_FIELDS} values={values} errors={errors} roles={roles} currentRole={initial?.role} onChange={(k, v) => setValues((prev) => ({ ...prev, [k]: v }))} autoFocusName />
      <div className="actions">
        <button type="button" className="btn small" onClick={() => void save()} disabled={busy}>
          {busy ? "Saving…" : "Save contact"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function RecruiterCompanyContacts({ companyId }: { companyId: string }) {
  const [list, setList] = useState<ContactList | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [roles, setRoles] = useState<CatalogueValue[]>([]);
  const [editing, setEditing] = useState<string | null>(null); // a contact id, "new", or null
  const [deactivating, setDeactivating] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const url = contactsOf(companyId);
  const addId = `company-${companyId}-add-contact`;
  const statusId = `company-${companyId}-contacts-status`;
  const canEdit = list?.can_edit ?? false;

  const load = useCallback(
    (signal?: AbortSignal) => {
      setLoadFailed(false);
      fetch(url, { signal })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((data) => (isContactList(data) ? setList(data) : Promise.reject(new Error("shape"))))
        .catch(() => !signal?.aborted && setLoadFailed(true));
    },
    [url],
  );
  useEffect(() => {
    const abort = new AbortController();
    load(abort.signal);
    return () => abort.abort();
  }, [load]);
  // The role picker is only needed by people who can edit; readers (manager, BDM) never load it.
  useEffect(() => {
    if (!canEdit) return;
    const abort = new AbortController();
    activeValues("contact-roles", abort.signal)
      .then(setRoles)
      .catch(() => undefined); // the editor still works; Role then offers only the stored value
    return () => abort.abort();
  }, [canEdit]);

  /** One write; on success the list re-renders and the status line says what happened. Returns field errors for the editor. */
  async function write(target: string, method: "POST" | "PATCH", body: Record<string, unknown>, text: string, returnTo = statusId): Promise<ContactErrors | null> {
    if (method === "PATCH" && Object.keys(body).length === 0) {
      setEditing(null);
      setNotice("No changes to save.");
      focus(returnTo);
      return null;
    }
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(target, method, body);
    setBusy(false);
    if (outcome.ok && isContactList(outcome.data)) {
      setList(outcome.data as ContactList);
      setEditing(null);
      setDeactivating(null);
      setNotice(text);
      focus(returnTo);
      return null;
    }
    const onFields = !outcome.ok && outcome.status === 422 ? contactErrorsOf(outcome.detail, ["body"]) : null;
    if (onFields) return onFields;
    setFailure(outcome.ok ? "Unable to update the contacts." : outcome.message);
    return null;
  }
  const close = (returnTo: string) => {
    setEditing(null);
    setDeactivating(null);
    focus(returnTo);
  };

  const summary = list && businessContacts(list.items);
  return (
    <section className="action-card wide" aria-labelledby={`company-${companyId}-contacts`} aria-busy={!list && !loadFailed}>
      <h3 id={`company-${companyId}-contacts`}>Contacts</h3>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {loadFailed && (
        <p className="form-error" role="alert">
          The contacts could not be loaded.{" "}
          <button type="button" className="btn secondary small" onClick={() => load()}>
            Retry
          </button>
        </p>
      )}
      {!list && !loadFailed && <p className="muted">Loading contacts…</p>}
      {list && summary && (
        <>
          <h4 style={{ margin: "4px 0" }}>Business contacts</h4>
          <DetailList
            rows={[
              ["HR contact", names(summary.hr)],
              ["Talent acquisition contact", names(summary.talentAcquisition)],
              ["Hiring manager", names(summary.hiringManager)],
              ["HR email", display(summary.hrEmail)],
              ["HR phone", display(summary.hrPhone)],
            ]}
          />
          <h4 style={{ margin: "12px 0 4px" }}>All contacts</h4>
          {list.items.length === 0 && <p className="muted">No contacts yet.{canEdit ? " Add the people you deal with at this company." : ""}</p>}
          <ul aria-label="Contacts" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
            {list.items.map((c) => {
              const editId = `contact-${c.id}-edit`;
              const deactivateId = `contact-${c.id}-deactivate`;
              return (
                <li key={c.id} className="card" style={{ padding: 14 }}>
                  {editing === c.id ? (
                    <ContactEditor initial={c} roles={roles} busy={busy} onSave={(body) => write(`${CONTACTS_URL}/${c.id}`, "PATCH", body, "Contact updated.", editId)} onCancel={() => close(editId)} />
                  ) : (
                    <>
                      <p style={{ margin: 0, fontWeight: 800, overflowWrap: "anywhere" }}>
                        {c.name} {c.is_primary && <span className="badge">Primary</span>} {!c.active && <span className="badge">Inactive</span>}
                      </p>
                      <DetailList rows={details(c)} />
                      {canEdit && (
                        <div className="actions" style={{ marginTop: 8 }}>
                          <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(c.id)} disabled={busy}>
                            Edit<span className="visually-hidden"> {c.name}</span>
                          </button>
                          {c.active && !c.is_primary && (
                            <button type="button" className="btn secondary small" onClick={() => void write(`${CONTACTS_URL}/${c.id}`, "PATCH", { is_primary: true }, `${c.name} is now the primary contact.`)} disabled={busy}>
                              Make primary<span className="visually-hidden"> {c.name}</span>
                            </button>
                          )}
                          {c.active ? (
                            <button id={deactivateId} type="button" className="btn secondary small" onClick={() => setDeactivating(c.id)} disabled={busy}>
                              Deactivate<span className="visually-hidden"> {c.name}</span>
                            </button>
                          ) : (
                            <button type="button" className="btn secondary small" onClick={() => void write(`${CONTACTS_URL}/${c.id}`, "PATCH", { active: true }, `${c.name} reactivated.`)} disabled={busy}>
                              Reactivate<span className="visually-hidden"> {c.name}</span>
                            </button>
                          )}
                        </div>
                      )}
                      {deactivating === c.id && (
                        <BdmConfirm
                          label="Confirm deactivate"
                          confirmText="Yes, deactivate"
                          busyText="Deactivating…"
                          cancelText="Keep active"
                          busy={busy}
                          onConfirm={() => void write(`${CONTACTS_URL}/${c.id}`, "PATCH", { active: false }, `${c.name} deactivated.`)}
                          onCancel={() => close(deactivateId)}
                        >
                          Deactivate {c.name}? They stay on the record and can be reactivated.
                          {c.is_primary && list.items.some((o) => o.active && o.id !== c.id) && " Make another contact primary first."}
                        </BdmConfirm>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
          {canEdit &&
            (editing === "new" ? (
              <ContactEditor roles={roles} busy={busy} onSave={(body) => write(url, "POST", body, "Contact added.", addId)} onCancel={() => close(addId)} />
            ) : (
              <div style={{ marginTop: 12 }}>
                <button id={addId} type="button" className="btn secondary small" onClick={() => setEditing("new")} disabled={busy || list.items.length >= MAX_CONTACTS}>
                  Add contact
                </button>
                {list.items.length >= MAX_CONTACTS && <p className="muted">A company can have at most {MAX_CONTACTS} contacts.</p>}
              </div>
            ))}
        </>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}
