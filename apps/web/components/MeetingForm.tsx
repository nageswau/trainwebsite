"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmPipeline";
import type { PickOption } from "@/lib/lookups";
import { LIMITS, LINK_MISSING_TEXT, type Meeting, MEETING_TYPES, MEETINGS_PATH, MEETINGS_URL, meetingPath, meetingUrl, MODES } from "@/lib/meetings";
import { contactsUrl } from "@/lib/universities";
import { employeeOptions, leadOptions, universityOptions } from "@/lib/visits";

// upc-009 (§7, MG1-MG8): schedule a university meeting, or edit / reschedule a scheduled one. Times are entered and shown in IST. The
// contact person and the university participants are the university's contacts (upc-006), loaded once it is known; the contact person
// always attends (the API stores it as a participant), so its box is ticked and fixed. EduSphere participants and, for a head, the
// responsible employee use upc-010's pickers. On edit only what changed is sent. The API decides every rule; its 422s land on the fields.
const TEXT = ["location", "meeting_url", "agenda", "notes"] as const;
type Draft = Record<(typeof TEXT)[number] | "meeting_type" | "start" | "mode" | "contact_id" | "reschedule_reason", string>;
const LABELS: Record<string, string> = {
  university_id: "University", responsible_user_id: "Responsible employee", meeting_type: "Meeting type", starts_at: "Date and time (IST)",
  location: "Location", meeting_url: "Meeting link", agenda: "Agenda", notes: "Notes", contact_id: "Contact person",
  participant_contact_ids: "University participants", participant_user_ids: "Participants from EduSphere", reschedule_reason: "Reason for the new time (optional)",
};
const SAVE_FAILED = "The meeting could not be saved. Try again.";
const MAX_EMPLOYEES = 10;

const draftOf = (m?: Meeting): Draft => ({
  meeting_type: m?.meeting_type ?? "", start: m ? isoToIstInput(m.starts_at) : "", mode: m?.mode ?? "offline", location: m?.location ?? "",
  meeting_url: m?.meeting_url ?? "", agenda: m?.agenda ?? "", notes: m?.notes ?? "", contact_id: m?.contact?.id ?? "", reschedule_reason: "",
});
const person = (p: { id: string; full_name: string }): PickOption => ({ id: p.id, label: p.full_name });
const sameIds = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
type Contact = { id: string; name: string; designation: string | null };

export default function MeetingForm({ meeting, university, canPickResponsible }: { meeting?: Meeting; university?: PickOption | null; canPickResponsible: boolean }) {
  const router = useRouter();
  const sending = useRef(false);
  const [draft, setDraft] = useState(() => draftOf(meeting));
  const [uni, setUni] = useState<PickOption | null>(meeting ? { id: meeting.university.id, label: meeting.university.name } : university ?? null);
  const [responsible, setResponsible] = useState<PickOption | null>(meeting && canPickResponsible ? person(meeting.responsible) : null);
  const [people, setPeople] = useState<PickOption[]>(() => (meeting?.participants.employees ?? []).map(person));
  const [pickerKey, setPickerKey] = useState(0);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  // University participants other than the contact person (the API always adds the contact person).
  const initialChosen = (meeting?.participants.contacts ?? []).map((c) => c.id).filter((id) => id !== meeting?.contact?.id);
  const [chosen, setChosen] = useState<string[]>(initialChosen);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!uni) return setContacts(null);
    const controller = new AbortController();
    fetch(`${contactsUrl(uni.id)}?limit=50`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setContacts(isPage<Contact>(data) ? data.items : []))
      .catch(() => controller.signal.aborted || setContacts([]));
    return () => controller.abort();
  }, [uni]);

  const set = (name: keyof Draft, value: string) => setDraft((d) => ({ ...d, [name]: value }));
  const a11y = (name: string) => (errors[name] ? { "aria-invalid": true as const, "aria-describedby": `meeting-${name}-error` } : {});
  const fieldError = (name: string) => errors[name] && <p className="form-error" id={`meeting-${name}-error`}>{errors[name]}</p>;
  const field = (name: string, control: ReactNode, id = `meeting-${name}`) => (
    <div className="field" key={name}>
      <label htmlFor={id}>{LABELS[name]}</label>
      {control}
      {fieldError(name)}
    </div>
  );
  const startChanged = Boolean(meeting) && draft.start !== draftOf(meeting).start;
  const linkMissing = draft.mode === "online" && !draft.meeting_url.trim();
  const contactPerson = contacts?.find((c) => c.id === draft.contact_id);
  const others = chosen.filter((id) => id !== draft.contact_id);

  function body(): Record<string, unknown> {
    const base = draftOf(meeting);
    const out: Record<string, unknown> = {};
    if (!meeting) out.university_id = uni?.id;
    for (const key of ["meeting_type", "mode"] as const) if (!meeting || draft[key] !== base[key]) out[key] = draft[key];
    if (!meeting || draft.start !== base.start) out.starts_at = istInputToIso(draft.start);
    for (const key of TEXT) {
      const value = draft[key].trim();
      if (meeting ? value !== base[key].trim() : value) out[key] = value || null;
    }
    if (meeting ? draft.contact_id !== base.contact_id : draft.contact_id) out.contact_id = draft.contact_id || null;
    if (canPickResponsible && responsible && responsible.id !== meeting?.responsible.id) out.responsible_user_id = responsible.id;
    const employees = people.map((p) => p.id);
    if (!meeting) return { ...out, participant_contact_ids: others, participant_user_ids: employees };
    if (!sameIds(others, initialChosen)) out.participant_contact_ids = others;
    if (!sameIds(employees, meeting.participants.employees.map((p) => p.id))) out.participant_user_ids = employees;
    if (startChanged && draft.reschedule_reason.trim()) out.reschedule_reason = draft.reschedule_reason.trim();
    return out;
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const missing: Record<string, string> = {};
    if (!uni) missing.university_id = "Choose a university";
    if (!draft.meeting_type) missing.meeting_type = "Choose the meeting type";
    if (!draft.start) missing.starts_at = "Choose the date and time";
    setErrors(missing);
    setFailure(null);
    if (Object.keys(missing).length) return;
    const payload = body();
    if (meeting && !Object.keys(payload).length) return router.push(meetingPath(meeting.id));
    sending.current = true;
    setBusy(true);
    const outcome = await sendJson(meeting ? meetingUrl(meeting.id) : MEETINGS_URL, meeting ? "PATCH" : "POST", payload);
    sending.current = false;
    setBusy(false);
    const saved = outcome.ok ? (outcome.data.meeting as { id?: string } | undefined) : undefined;
    if (saved?.id) return router.push(meetingPath(saved.id));
    if (outcome.ok) return setFailure(SAVE_FAILED);
    const mapped = outcome.status === 422 ? fieldErrors(outcome.detail) : {};
    setErrors(mapped);
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const text = (name: (typeof TEXT)[number]) =>
    field(name, name === "agenda" || name === "notes" ? (
      <textarea id={`meeting-${name}`} rows={3} maxLength={LIMITS[name]} value={draft[name]} disabled={busy} onChange={(e) => set(name, e.target.value)} {...a11y(name)} />
    ) : (
      <input id={`meeting-${name}`} type={name === "meeting_url" ? "url" : "text"} maxLength={LIMITS[name]} value={draft[name]} disabled={busy}
        placeholder={name === "meeting_url" ? "https://" : undefined} onChange={(e) => set(name, e.target.value)} {...a11y(name)} />
    ));

  return (
    <form onSubmit={save} noValidate aria-label={meeting ? `Edit ${meeting.code}` : "Schedule a university meeting"} style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {uni && (meeting || university) ? (
          <div className="field">
            <span className="muted">University</span>
            <p style={{ margin: "4px 0 0", fontWeight: 700 }}>{uni.label}</p>
            {university?.detail && <p className="muted" style={{ margin: 0 }}>{university.detail}</p>}
          </div>
        ) : (
          <div>
            <SearchableSelect id="meeting-university_id" label="University" noun="university" search={universityOptions} disabled={busy}
              onChange={(option) => { setUni(option); setChosen([]); set("contact_id", ""); }} />
            {fieldError("university_id")}
          </div>
        )}
        {canPickResponsible && (
          <div>
            <SearchableSelect id="meeting-responsible_user_id" label={LABELS.responsible_user_id} noun="manager" search={leadOptions} initial={responsible}
              disabled={busy} onChange={setResponsible} />
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>Leave empty to be responsible yourself.</p>
            {fieldError("responsible_user_id")}
          </div>
        )}
        {field("meeting_type", (
          <select id="meeting-meeting_type" value={draft.meeting_type} disabled={busy} onChange={(e) => set("meeting_type", e.target.value)} {...a11y("meeting_type")}>
            <option value="">Choose a type</option>
            {Object.entries(MEETING_TYPES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
          </select>
        ))}
        {field("starts_at", (
          <input id="meeting-starts_at" type="datetime-local" min={nowIstInput()} value={draft.start} disabled={busy} onChange={(e) => set("start", e.target.value)} {...a11y("starts_at")} />
        ))}
        {startChanged && field("reschedule_reason", (
          <input id="meeting-reschedule_reason" maxLength={500} value={draft.reschedule_reason} disabled={busy} onChange={(e) => set("reschedule_reason", e.target.value)} {...a11y("reschedule_reason")} />
        ))}
      </div>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 12 }}>
        <legend>Where</legend>
        <div role="radiogroup" aria-label="Online or offline" style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          {Object.entries(MODES).map(([key, word]) => (
            <label key={key} style={{ display: "inline-flex", gap: 6, alignItems: "center", minHeight: 32 }}>
              <input type="radio" name="meeting-mode" value={key} checked={draft.mode === key} disabled={busy} onChange={() => set("mode", key)} /> {word}
            </label>
          ))}
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
          {text("location")}
          {text("meeting_url")}
        </div>
        {linkMissing && <p className="notice" role="note" style={{ margin: 0 }}>{LINK_MISSING_TEXT}</p>}
      </fieldset>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 10 }} disabled={busy}>
        <legend>University side</legend>
        {!uni ? <p className="muted" style={{ margin: 0 }}>Choose the university first.</p>
          : contacts === null ? <p className="muted" style={{ margin: 0 }}>Loading contacts…</p>
          : contacts.length === 0 ? <p className="muted" style={{ margin: 0 }}>No contacts recorded for this university yet.</p>
          : (
            <>
              {field("contact_id", (
                <select id="meeting-contact_id" value={draft.contact_id} onChange={(e) => set("contact_id", e.target.value)} {...a11y("contact_id")}>
                  <option value="">No contact person</option>
                  {/* a stored contact person since deleted from the university stays selectable by its copied name */}
                  {meeting?.contact?.id && !contacts.some((c) => c.id === meeting.contact?.id) && <option value={meeting.contact.id}>{meeting.contact.name}</option>}
                  {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              ))}
              {contactPerson && <p className="muted" style={{ margin: 0 }}>Designation: {contactPerson.designation || "not recorded"}</p>}
              <div role="group" aria-labelledby="meeting-uni-participants" style={{ display: "grid", gap: 6 }}>
                <span id="meeting-uni-participants" className="muted">{LABELS.participant_contact_ids}</span>
                {contacts.map((c) => {
                  const isContactPerson = c.id === draft.contact_id;
                  return (
                    <label key={c.id} style={{ display: "inline-flex", gap: 6, alignItems: "center", minHeight: 28 }}>
                      <input type="checkbox" checked={isContactPerson || chosen.includes(c.id)} disabled={isContactPerson}
                        onChange={(e) => setChosen((list) => (e.target.checked ? [...list, c.id] : list.filter((id) => id !== c.id)))} />
                      {c.name}
                      {c.designation && <span className="muted">— {c.designation}</span>}
                      {isContactPerson && <span className="muted">(contact person)</span>}
                    </label>
                  );
                })}
              </div>
              {fieldError("participant_contact_ids")}
            </>
          )}
      </fieldset>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 10 }}>
        <legend>{LABELS.participant_user_ids}</legend>
        {people.length > 0 && (
          <ul aria-label="EduSphere participants" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {people.map((p) => (
              <li key={p.id} className="badge" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                {p.label}
                <button type="button" className="btn ghost small" aria-label={`Remove ${p.label}`} disabled={busy}
                  onClick={() => setPeople((list) => list.filter((x) => x.id !== p.id))}>×</button>
              </li>
            ))}
          </ul>
        )}
        <SearchableSelect key={pickerKey} id="meeting-participant" label="Add an employee" noun="employee" search={employeeOptions} disabled={busy || people.length >= MAX_EMPLOYEES}
          onChange={(option) => {
            if (option && !people.some((p) => p.id === option.id)) setPeople((list) => [...list, option]);
            if (option) setPickerKey((k) => k + 1);
          }} />
        {fieldError("participant_user_ids")}
      </fieldset>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {text("agenda")}
        {text("notes")}
      </div>
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : meeting ? "Save meeting" : "Schedule meeting"}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={() => router.push(meeting ? meetingPath(meeting.id) : MEETINGS_PATH)}>Cancel</button>
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </form>
  );
}
