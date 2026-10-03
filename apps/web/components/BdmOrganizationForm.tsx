"use client";
import { type FormEvent, useRef, useState } from "react";

import BdmContactFields, { blankContact, type ContactValues } from "@/components/BdmContactFields";
import BdmOrganizationFields, { ORG_FIELDS, type OrgField, type OrgValues } from "@/components/BdmOrganizationFields";
import BdmOrganizationProfileFields, { filledFields, profileErrors, profilePayload, profileValuesOf, type ProfileValues } from "@/components/BdmOrganizationProfileFields";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import {
  ALL_PROFILE_FIELDS,
  isOrganizationBody,
  type Organization,
  orgDuplicate,
  type OrgDuplicate,
  ORGS_URL,
  profileGroup,
  profileNotEmpty,
  type ProfileField,
  saveClearedFirst,
  typeChangeMessage,
} from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";
import { plural } from "@/lib/plural";

// bdm-002 (spec §6.2, §12.2): add or edit an organization. A likely duplicate is the server's 409; the BDM decides, and "Save
// anyway" resends the same entry with confirm_duplicate (AC2, the AgentStudentForm pattern). The matches are plain text, so
// following one can't lose the unsaved entry. The entry is never cleared on an error.
const LEAVE_PROMPT = "You have unsaved changes to this organization. Leave without saving?";
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
    address: o?.address ?? "",
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

type ServerErrors = { org: Partial<Record<OrgField, string>>; contact: Record<string, string>; profile: Partial<Record<ProfileField, string>> };

/** FastAPI's 422 list -> errors on the organization's own fields (`["body", field]`), on a profile field (`["body", "profile", field]`,
 * bdm-003) or on the contact they belong to (`["body", "contacts", i, field]`, keyed like BdmContactFields). Null when any item maps to
 * none of these: the form then shows the whole detail as one message, so nothing is hidden (final review I1). */
function serverErrors(detail: unknown, contacts: ContactValues[]): ServerErrors | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const org: Partial<Record<OrgField, string>> = {};
  const contact: Record<string, string> = {};
  const profile: Partial<Record<ProfileField, string>> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const [where, field, index, contactField] = item?.loc ?? [];
    const message = detailMessage([item]);
    if (where !== "body") return null;
    if (item.loc!.length === 2 && ORG_FIELDS.includes(field as OrgField)) org[field as OrgField] = message;
    else if (item.loc!.length === 4 && field === "contacts" && typeof index === "number" && contacts[index] && typeof contactField === "string") {
      contact[`${contacts[index].key}-${contactField}`] = message;
    } else if (item.loc!.length === 3 && field === "profile" && ALL_PROFILE_FIELDS.includes(index as ProfileField)) profile[index as ProfileField] = message;
    else return null;
  }
  return { org, contact, profile };
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
  /** `saved` is false when there was nothing to change (browser QA-13). */
  onSaved: (o: Organization, saved: boolean) => void;
  onCancel: () => void;
}) {
  const original = useRef(valuesOf(organization));
  const [values, setValues] = useState<OrgValues>(original.current);
  const [contacts, setContacts] = useState<ContactValues[]>(() => [blankContact("c1", true)]);
  // bdm-003: the profile holds every group's values; only the current type's group is shown and sent (switching back restores it).
  const originalProfile = useRef(profileValuesOf(organization?.profile));
  const [profile, setProfile] = useState<ProfileValues>(originalProfile.current);
  const [profileErrs, setProfileErrs] = useState<Partial<Record<ProfileField, string>>>({});
  const group = profileGroup(values.org_type);
  const originalGroup = profileGroup(original.current.org_type);
  const [errors, setErrors] = useState<Partial<Record<OrgField, string>>>({});
  const [contactErrors, setContactErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<OrgDuplicate | null>(null);
  const [busy, setBusy] = useState(false);
  const focus = useFocusAfterRender();
  const idPrefix = mode === "create" ? "org-new" : `org-${organization?.id}`;
  const dirty =
    ORG_FIELDS.some((k) => values[k] !== original.current[k]) ||
    ALL_PROFILE_FIELDS.some((k) => profile[k] !== originalProfile.current[k]) ||
    (mode === "create" && contacts.some((c) => [c.name, c.designation, c.role, c.phone, c.email].some((v) => v.trim())));

  // Browser QA-11: unsaved input is not thrown away silently: Cancel, in-app links, reload and close ask first.
  useLeaveGuard(dirty, LEAVE_PROMPT);

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function payload(): Record<string, unknown> {
    if (mode === "edit") {
      const changed: Record<string, unknown> = Object.fromEntries(ORG_FIELDS.filter((k) => values[k] !== original.current[k]).map((k) => [k, wire(k, values[k])]));
      const p = profilePayload(group, profile, originalProfile.current);
      if (p) changed.profile = p;
      return changed;
    }
    const body: Record<string, unknown> = Object.fromEntries(ORG_FIELDS.map((k) => [k, wire(k, values[k])]).filter(([, v]) => v !== null));
    const p = profilePayload(group, profile);
    if (p) body.profile = p;
    body.contacts = contacts.map(contactBody);
    return body;
  }

  /** Client-side checks (a convenience; the server decides). Focuses the first problem. */
  function check(): boolean {
    const found: Partial<Record<OrgField, string>> = {};
    for (const [key, message] of REQUIRED) if (!String(values[key]).trim()) found[key] = message;
    if (mode === "edit" && originalGroup && group !== originalGroup) {
      const filled = filledFields(originalGroup, originalProfile.current);
      // P4: the server's 409 is the authority. Details cleared in this form are not saved yet (only the new type's group is sent), so
      // say how to get there in two saves rather than repeat "clear them" (final review I2).
      if (filled.length) found.org_type = filledFields(originalGroup, profile).length ? typeChangeMessage(originalGroup, filled) : saveClearedFirst(originalGroup);
    }
    const foundProfile = profileErrors(group, profile);
    const foundContacts: Record<string, string> = {};
    if (mode === "create") for (const c of contacts) if (!c.name.trim()) foundContacts[`${c.key}-name`] = "Contact name is required";
    setErrors(found);
    setProfileErrs(foundProfile);
    setContactErrors(foundContacts);
    const first = Object.keys(found)[0] ?? Object.keys(foundProfile)[0] ?? Object.keys(foundContacts)[0];
    if (first) focus(`${idPrefix}-${first}`);
    return !first;
  }

  async function save(confirm = false) {
    if (busy || !check()) return;
    const body = payload();
    if (mode === "edit" && Object.keys(body).length === 0) return onSaved(organization!, false);
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
        onSaved(data.organization, true);
        return;
      }
      const dup = response.status === 409 ? orgDuplicate(data?.detail) : null;
      const notEmpty = response.status === 409 ? profileNotEmpty(data?.detail) : null;
      const onFields = response.status === 422 ? serverErrors(data?.detail, contacts) : null;
      if (dup) {
        setDuplicate(dup);
        focus(`${idPrefix}-duplicate`);
      } else if (notEmpty) {
        // bdm-003 P4: worded with the stored group when the form knows it, else with the server's own message.
        setErrors({ org_type: originalGroup ? typeChangeMessage(originalGroup, notEmpty) : `${String(data?.detail?.message ?? "Clear the details before changing the type")}.` });
        focus(`${idPrefix}-org_type`);
      } else if (onFields) {
        setErrors(onFields.org);
        setProfileErrs(onFields.profile);
        setContactErrors(onFields.contact);
        const first = ORG_FIELDS.find((k) => onFields.org[k]) ?? ALL_PROFILE_FIELDS.find((k) => onFields.profile[k]) ?? Object.keys(onFields.contact)[0];
        focus(`${idPrefix}-${first}`);
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
      <BdmOrganizationProfileFields idPrefix={idPrefix} group={group} values={profile} errors={profileErrs} onChange={(k, v) => setProfile((prev) => ({ ...prev, [k]: v }))} />
      {mode === "create" && <BdmContactFields idPrefix={idPrefix} contacts={contacts} errors={contactErrors} onChange={setContacts} orgType={values.org_type} />}
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
          {duplicate.total > duplicate.matches.length && <p>{plural(duplicate.total - duplicate.matches.length, "more similar organization", "more similar organizations")}.</p>}
          <button type="button" className="btn small" onClick={() => void save(true)} disabled={busy}>
            Save anyway
          </button>{" "}
          <button
            type="button"
            className="btn secondary small"
            onClick={() => {
              setDuplicate(null);
              focus(`${idPrefix}-save`); // browser QA-10: the warning (and the focused control) is gone
            }}
          >
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
        <button id={`${idPrefix}-save`} type="submit" className="btn small" disabled={busy || duplicate !== null}>
          {busy ? "Saving…" : mode === "create" ? "Save organization" : "Save changes"}
        </button>
        <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}
