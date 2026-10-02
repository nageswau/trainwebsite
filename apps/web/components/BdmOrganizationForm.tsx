"use client";
import { type FormEvent, useRef, useState } from "react";

import BdmContactFields, { blankContact, type ContactValues } from "@/components/BdmContactFields";
import BdmOrganizationFields, { type OrgField, type OrgValues } from "@/components/BdmOrganizationFields";
import { fieldErrors } from "@/lib/agentStudents";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { isOrganizationBody, type Organization, orgDuplicate, type OrgDuplicate, ORGS_URL } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 (spec §6.2, §12.2): add or edit an organization. A likely duplicate is the server's 409; the BDM decides, and "Save
// anyway" resends the same entry with confirm_duplicate (AC2, the AgentStudentForm pattern). The matches are plain text, so
// following one can't lose the unsaved entry. The entry is never cleared on an error.
const ORG_FIELDS: OrgField[] = ["org_type", "name", "city", "state", "phone", "email", "website", "existing_partner", "courses_interested", "student_count"];
const REQUIRED: [OrgField, string][] = [
  ["org_type", "Choose a type"],
  ["name", "Organization name is required"],
  ["city", "City is required"],
];

function valuesOf(o?: Organization): OrgValues {
  return {
    org_type: o?.org_type ?? "",
    name: o?.name ?? "",
    city: o?.city ?? "",
    state: o?.state ?? "",
    phone: o?.phone ?? "",
    email: o?.email ?? "",
    website: o?.website ?? "",
    existing_partner: o?.existing_partner ?? false,
    courses_interested: o?.courses_interested ?? "",
    student_count: o?.student_count == null ? "" : String(o.student_count),
  };
}

/** A form value as the API expects it: blank text is null (clears on edit), the student count is a number. */
function wire(key: OrgField, value: string | boolean): unknown {
  if (typeof value === "boolean") return value;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return key === "student_count" ? Number(trimmed) : trimmed;
}

function contactBody(c: ContactValues): Record<string, unknown> {
  const body: Record<string, unknown> = { name: c.name.trim(), is_primary: c.is_primary };
  for (const key of ["designation", "role", "phone", "email"] as const) if (c[key].trim()) body[key] = c[key].trim();
  return body;
}

export default function BdmOrganizationForm({
  mode,
  organization,
  onSaved,
  onCancel,
}: {
  mode: "create" | "edit";
  organization?: Organization;
  onSaved: (o: Organization) => void;
  onCancel: () => void;
}) {
  const original = useRef(valuesOf(organization));
  const [values, setValues] = useState<OrgValues>(original.current);
  const [contacts, setContacts] = useState<ContactValues[]>(() => [blankContact(true)]);
  const [errors, setErrors] = useState<Partial<Record<OrgField, string>>>({});
  const [contactErrors, setContactErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<OrgDuplicate | null>(null);
  const [busy, setBusy] = useState(false);
  const focus = useFocusAfterRender();
  const idPrefix = mode === "create" ? "org-new" : `org-${organization?.id}`;

  function payload(): Record<string, unknown> {
    if (mode === "edit") {
      return Object.fromEntries(ORG_FIELDS.filter((k) => values[k] !== original.current[k]).map((k) => [k, wire(k, values[k])]));
    }
    const body: Record<string, unknown> = Object.fromEntries(ORG_FIELDS.map((k) => [k, wire(k, values[k])]).filter(([, v]) => v !== null));
    body.contacts = contacts.map(contactBody);
    return body;
  }

  /** Client-side required checks (a convenience; the server decides). Focuses the first problem. */
  function check(): boolean {
    const found: Partial<Record<OrgField, string>> = {};
    for (const [key, message] of REQUIRED) if (!String(values[key]).trim()) found[key] = message;
    const foundContacts: Record<string, string> = {};
    if (mode === "create") for (const c of contacts) if (!c.name.trim()) foundContacts[`${c.key}-name`] = "Contact name is required";
    setErrors(found);
    setContactErrors(foundContacts);
    const first = Object.keys(found)[0] ?? Object.keys(foundContacts)[0];
    if (first) focus(`${idPrefix}-${first}`);
    return !first;
  }

  async function save(confirm = false) {
    if (busy || !check()) return;
    const body = payload();
    if (mode === "edit" && Object.keys(body).length === 0) return onSaved(organization!);
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "create" ? ORGS_URL : `${ORGS_URL}/${organization!.id}`, {
        method: mode === "create" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(confirm ? { ...body, confirm_duplicate: true } : body),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && isOrganizationBody(data)) {
        setDuplicate(null);
        onSaved(data.organization);
        return;
      }
      const dup = response.status === 409 ? orgDuplicate(data?.detail) : null;
      const onFields = response.status === 422 ? fieldErrors(data?.detail, ORG_FIELDS) : null;
      if (dup) {
        setDuplicate(dup);
        focus(`${idPrefix}-duplicate`);
      } else if (onFields) {
        setErrors(onFields);
        focus(`${idPrefix}-${ORG_FIELDS.find((k) => onFields[k])}`);
      } else {
        setFailure(detailMessage(data?.detail, "Unable to save this organization."));
        focus(`${idPrefix}-failure`);
      }
    } catch {
      setFailure(NOT_COMPLETED);
      focus(`${idPrefix}-failure`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="form"
      noValidate
      aria-busy={busy}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        void save();
      }}
    >
      <BdmOrganizationFields idPrefix={idPrefix} values={values} errors={errors} onChange={(k, v) => setValues((prev) => ({ ...prev, [k]: v }))} />
      {mode === "create" && <BdmContactFields idPrefix={idPrefix} contacts={contacts} errors={contactErrors} onChange={setContacts} />}
      {duplicate && (
        <div role="alert" className="form-error">
          <h4 id={`${idPrefix}-duplicate`} tabIndex={-1} style={{ margin: "0 0 8px" }}>
            {duplicate.message}
          </h4>
          <ul>
            {duplicate.matches.map((m) => (
              <li key={m.id}>
                {m.code} — {m.name}, {m.city} · assigned to {m.assigned_bdm_name}
                {m.archived ? " · Archived" : ""}
              </li>
            ))}
          </ul>
          {duplicate.total > duplicate.matches.length && <p>{duplicate.total - duplicate.matches.length} more similar organizations.</p>}
          <button type="button" className="btn small" onClick={() => void save(true)} disabled={busy}>
            Save anyway
          </button>{" "}
          <button type="button" className="btn secondary small" onClick={() => setDuplicate(null)}>
            Go back
          </button>
        </div>
      )}
      {failure && (
        <p className="form-error" role="alert" id={`${idPrefix}-failure`} tabIndex={-1}>
          {failure}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || duplicate !== null}>
          {busy ? "Saving…" : mode === "create" ? "Save organization" : "Save changes"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}
