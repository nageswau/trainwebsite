"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import BdmAppointmentFields, { type FieldValues } from "@/components/BdmAppointmentFields";
import BdmOverlapAlert from "@/components/BdmOverlapAlert";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, isoToIstInput, istInputToIso, myOrganizationSearch, type Overlap, overlap as readOverlap } from "@/lib/bdmAppointments";
import { isOrganizationBody, LINK_STYLE, type OrgContact, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";

// bdm-006 (spec §6.2, R-F3-R-F6): book an appointment (create) or edit an open one (edit: no time -- that is Reschedule). The API
// decides every rule; this form keeps the entry on any failure and shows the message. Any
// field change clears the overlap warning, and the warning keeps the exact body that was checked: "Save anyway" resends that body, never
// the current fields (an edit made while the request was pending cannot be confirmed unchecked).
type Props =
  | { mode: "create"; bdmType: BdmType; initialOrganization: Organization | null }
  | { mode: "edit"; bdmType: BdmType; appointment: Appointment; onSaved: (a: Appointment, saved: boolean) => void; onCancel: () => void };

const primaryOf = (contacts: OrgContact[]) => (contacts.find((c) => c.is_primary) ?? contacts[0])?.id ?? "";
const text = (v: string | null) => v ?? "";
const orNull = (v: string) => (v.trim() === "" ? null : v.trim());

function initialValues(props: Props): FieldValues {
  if (props.mode === "edit") {
    const a = props.appointment;
    return {
      contactId: a.contact_id ?? "", when: isoToIstInput(a.starts_at), duration: a.duration_minutes, type: a.appointment_type, location: text(a.location),
      purpose: text(a.purpose), remarks: text(a.remarks), leads: a.expected_leads === null ? "" : String(a.expected_leads), revenue: text(a.expected_revenue),
    };
  }
  return { contactId: primaryOf(props.initialOrganization?.contacts ?? []), when: "", duration: 60, type: "", location: "", purpose: "", remarks: "", leads: "", revenue: "" };
}

export default function BdmAppointmentForm(props: Props) {
  const router = useRouter();
  const editing = props.mode === "edit" ? props.appointment : null;
  const [orgId, setOrgId] = useState(editing?.organization.id ?? (props.mode === "create" ? props.initialOrganization?.id ?? "" : ""));
  const [contacts, setContacts] = useState<OrgContact[] | null>(props.mode === "create" ? props.initialOrganization?.contacts ?? null : null);
  const [contactsLoading, setContactsLoading] = useState(props.mode === "edit");
  const [values, setValues] = useState<FieldValues>(() => initialValues(props));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [warning, setWarning] = useState<{ overlap: Overlap; body: Record<string, unknown> } | null>(null);
  const set = <K extends keyof FieldValues>(key: K, value: FieldValues[K]) => {
    setWarning(null);
    setValues((v) => ({ ...v, [key]: value }));
  };

  async function loadContacts(id: string, keepChoice: boolean) {
    setContactsLoading(true);
    const response = await fetch(`${ORGS_URL}/${id}`).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    setContactsLoading(false);
    if (!isOrganizationBody(body)) return setMessage({ text: "Unable to load this organization's contacts.", failed: true });
    setContacts(body.organization.contacts);
    if (!keepChoice) set("contactId", primaryOf(body.organization.contacts));
  }
  useEffect(() => {
    if (editing) void loadContacts(editing.organization.id, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, for the appointment being edited
  }, []);

  function changedFields(a: Appointment): Record<string, unknown> {
    const next: Record<string, unknown> = {
      contact_id: values.contactId || a.contact_id, duration_minutes: values.duration, appointment_type: values.type,
      location: orNull(values.location), purpose: orNull(values.purpose), remarks: orNull(values.remarks),
      expected_leads: values.leads === "" ? null : Number(values.leads), expected_revenue: orNull(values.revenue),
    };
    const before: Record<string, unknown> = {
      contact_id: a.contact_id, duration_minutes: a.duration_minutes, appointment_type: a.appointment_type, location: a.location, purpose: a.purpose,
      remarks: a.remarks, expected_leads: a.expected_leads, expected_revenue: a.expected_revenue === null ? null : String(Number(a.expected_revenue)),
    };
    if (next.expected_revenue !== null) next.expected_revenue = String(Number(next.expected_revenue));
    return Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== before[k]));
  }

  async function send(body: Record<string, unknown>, confirmOverlap: boolean) {
    setMessage(null);
    setBusy(true);
    if (editing) {
      const outcome = await sendJson(`${APPOINTMENTS_URL}/${editing.id}`, "PATCH", confirmOverlap ? { ...body, confirm_overlap: true } : body);
      setBusy(false);
      return handle(outcome, body, (a) => props.mode === "edit" && props.onSaved(a, true));
    }
    const outcome = await sendJson(APPOINTMENTS_URL, "POST", { ...body, confirm_overlap: confirmOverlap });
    setBusy(false);
    handle(outcome, body, (a) => router.push(`/bdm/appointments/${a.id}?created=1`));
  }

  function submit() {
    if (editing) {
      const body = changedFields(editing);
      if (!Object.keys(body).length) return props.mode === "edit" && props.onSaved(editing, false);
      return void send(body, false);
    }
    void send(
      {
        organization_id: orgId, contact_id: values.contactId, starts_at: istInputToIso(values.when), duration_minutes: values.duration, appointment_type: values.type,
        location: orNull(values.location), purpose: orNull(values.purpose), remarks: orNull(values.remarks),
        expected_leads: values.leads === "" ? null : Number(values.leads), expected_revenue: orNull(values.revenue),
      },
      false,
    );
  }

  function handle(outcome: Awaited<ReturnType<typeof sendJson>>, body: Record<string, unknown>, onOk: (a: Appointment) => void) {
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setWarning(null);
      return onOk(outcome.data.appointment);
    }
    if (!outcome.ok && outcome.status === 409) {
      const clash = readOverlap(outcome.detail);
      if (clash) return setWarning({ overlap: clash, body });
    }
    setWarning(null);
    setMessage({ text: outcome.ok ? "Unable to save this appointment." : outcome.message, failed: true });
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };
  const deletedContact = editing && editing.contact_id === null && !values.contactId;

  return (
    <form onSubmit={onSubmit} aria-label={editing ? "Edit appointment" : "Book appointment"}>
      {!editing && (
        <SearchableSelect
          label="Organization (required)"
          noun="organization"
          required
          search={myOrganizationSearch()}
          initial={props.mode === "create" && props.initialOrganization ? { id: props.initialOrganization.id, label: props.initialOrganization.name, detail: props.initialOrganization.code } : null}
          onChange={(option) => {
            setOrgId(option?.id ?? "");
            setContacts(null);
            set("contactId", "");
            if (option) void loadContacts(option.id, false);
          }}
        />
      )}
      {!editing && (
        <p className="muted" style={{ marginTop: 4 }}>
          Only organizations assigned to you can be booked.{" "}
          <Link href="/bdm/organizations" style={LINK_STYLE}>
            Open organizations
          </Link>
        </p>
      )}
      {deletedContact && (
        <p className="muted" role="note">
          The booked contact ({editing.contact_name}) was removed from the organization. Choose another contact to change it, or leave it as recorded.
        </p>
      )}
      <BdmAppointmentFields values={values} set={set} bdmType={props.bdmType} contacts={contacts} contactsLoading={contactsLoading} showWhen={!editing} contactRequired={!(editing && editing.contact_id === null)} />
      {message && <FormMessage message={message} />}
      {warning && <BdmOverlapAlert overlap={warning.overlap} busy={busy} onConfirm={() => void send(warning.body, true)} onCancel={() => setWarning(null)} />}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy || warning !== null || (!editing && (!orgId || !values.contactId))}>
          {busy ? "Saving…" : editing ? "Save changes" : "Book appointment"}
        </button>
        {editing && props.mode === "edit" && (
          <button type="button" className="btn secondary" onClick={props.onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
