"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import type { PickOption } from "@/lib/lookups";
import { CALENDAR_PATH, EVENT_KINDS, EVENT_LIMITS, eventPath, eventUrl, EVENTS_URL, KIND_LABELS, type PartnershipEvent } from "@/lib/partnershipCalendar";
import { employeeOptions, indiaToday, leadOptions, universityOptions } from "@/lib/visits";

// upc-011 (§9, CL2-CL5): add a partnership event (conference, education fair, webinar...) or edit a scheduled one. Events are all-day,
// possibly several days; the university is optional. The owner (a head may pick a direct report) and the other employees use upc-010's
// pickers. On edit only what changed is sent. The API decides every rule; its 422s land on the fields. After saving, the event page shows
// any overlap with the people's other plans (AC2).
const TEXT = ["title", "location", "notes"] as const;
type Draft = Record<(typeof TEXT)[number] | "kind" | "starts_on" | "ends_on", string>;
const LABELS: Record<string, string> = {
  kind: "Event type", title: "Title", university_id: "University (optional)", starts_on: "Start date", ends_on: "End date", location: "Location",
  notes: "Notes", owner_user_id: "Owner", participant_user_ids: "Other employees",
};
const SAVE_FAILED = "The event could not be saved. Try again.";

const draftOf = (e?: PartnershipEvent): Draft => ({
  kind: e?.kind ?? "", title: e?.title ?? "", starts_on: e?.starts_on ?? "", ends_on: e?.ends_on ?? "", location: e?.location ?? "", notes: e?.notes ?? "",
});
const person = (p: { id: string; full_name: string }): PickOption => ({ id: p.id, label: p.full_name });
const sameIds = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

export default function PartnershipEventForm({ event, canPickOwner }: { event?: PartnershipEvent; canPickOwner: boolean }) {
  const router = useRouter();
  const sending = useRef(false);
  const [draft, setDraft] = useState(() => draftOf(event));
  const [uni, setUni] = useState<PickOption | null>(event?.university ? { id: event.university.id, label: event.university.name } : null);
  const [owner, setOwner] = useState<PickOption | null>(event && canPickOwner ? person(event.owner) : null);
  const [people, setPeople] = useState<PickOption[]>(() => (event?.participants ?? []).map(person));
  const [pickerKey, setPickerKey] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = indiaToday();

  const set = (name: keyof Draft, value: string) => setDraft((d) => ({ ...d, [name]: value }));
  const a11y = (name: string) => (errors[name] ? { "aria-invalid": true as const, "aria-describedby": `event-${name}-error` } : {});
  const fieldError = (name: string) => errors[name] && <p className="form-error" id={`event-${name}-error`}>{errors[name]}</p>;
  const field = (name: string, control: ReactNode) => (
    <div className="field" key={name}>
      <label htmlFor={`event-${name}`}>{LABELS[name]}</label>
      {control}
      {fieldError(name)}
    </div>
  );

  function body(): Record<string, unknown> {
    const base = draftOf(event);
    const out: Record<string, unknown> = {};
    for (const key of ["kind", "starts_on", "ends_on"] as const) if (!event || draft[key] !== base[key]) out[key] = draft[key];
    for (const key of TEXT) {
      const value = draft[key].trim();
      if (event ? value !== base[key].trim() : value) out[key] = value || null;
    }
    if (event ? (uni?.id ?? null) !== (event.university?.id ?? null) : uni) out.university_id = uni?.id ?? null;
    if (canPickOwner && owner && owner.id !== event?.owner.id) out.owner_user_id = owner.id;
    const employees = people.map((p) => p.id);
    if (!event) return { ...out, participant_user_ids: employees };
    if (!sameIds(employees, event.participants.map((p) => p.id))) out.participant_user_ids = employees;
    return out;
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (sending.current) return;
    const missing: Record<string, string> = {};
    if (!draft.kind) missing.kind = "Choose the event type";
    if (!draft.title.trim()) missing.title = "Give the event a title";
    if (!draft.starts_on) missing.starts_on = "Choose the start date";
    if (!draft.ends_on) missing.ends_on = "Choose the end date";
    else if (draft.starts_on && draft.ends_on < draft.starts_on) missing.ends_on = "The end date can't be before the start date";
    setErrors(missing);
    setFailure(null);
    if (Object.keys(missing).length) return;
    const payload = body();
    if (event && !Object.keys(payload).length) return router.push(eventPath(event.id));
    sending.current = true;
    setBusy(true);
    const outcome = await sendJson(event ? eventUrl(event.id) : EVENTS_URL, event ? "PATCH" : "POST", payload);
    sending.current = false;
    setBusy(false);
    const saved = outcome.ok ? (outcome.data.event as { id?: string } | undefined) : undefined;
    if (saved?.id) {
      router.push(eventPath(saved.id));
      router.refresh(); // upc-009 QA-01: a page visited moments ago would otherwise come from the router cache
      return;
    }
    if (outcome.ok) return setFailure(SAVE_FAILED);
    const mapped = outcome.status === 422 ? fieldErrors(outcome.detail) : {};
    setErrors(mapped);
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const date = (name: "starts_on" | "ends_on") =>
    field(name, (
      <input id={`event-${name}`} type="date" min={name === "ends_on" && draft.starts_on > today ? draft.starts_on : today} value={draft[name]} disabled={busy}
        onChange={(e) => set(name, e.target.value)} {...a11y(name)} />
    ));

  return (
    <form onSubmit={save} noValidate aria-label={event ? `Edit ${event.code}` : "Add a partnership event"} style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", alignItems: "start" }}>
        {field("kind", (
          <select id="event-kind" value={draft.kind} disabled={busy} onChange={(e) => set("kind", e.target.value)} {...a11y("kind")}>
            <option value="">Choose a type</option>
            {EVENT_KINDS.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
          </select>
        ))}
        {field("title", (
          <input id="event-title" maxLength={EVENT_LIMITS.title} value={draft.title} disabled={busy} onChange={(e) => set("title", e.target.value)} {...a11y("title")} />
        ))}
        {date("starts_on")}
        {date("ends_on")}
      </div>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", alignItems: "start" }}>
        <div>
          <SearchableSelect id="event-university_id" label={LABELS.university_id} noun="university" search={universityOptions} initial={uni} disabled={busy} onChange={setUni} />
          {fieldError("university_id")}
        </div>
        {field("location", (
          <input id="event-location" maxLength={EVENT_LIMITS.location} value={draft.location} disabled={busy} onChange={(e) => set("location", e.target.value)} {...a11y("location")} />
        ))}
        {canPickOwner && (
          <div>
            <SearchableSelect id="event-owner_user_id" label={LABELS.owner_user_id} noun="manager" search={leadOptions} initial={owner} disabled={busy} onChange={setOwner} />
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>Leave empty to own it yourself.</p>
            {fieldError("owner_user_id")}
          </div>
        )}
      </div>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 10 }}>
        <legend>{LABELS.participant_user_ids}</legend>
        {people.length > 0 && (
          <ul aria-label="Other employees at the event" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {people.map((p) => (
              <li key={p.id} className="badge" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                {p.label}
                <button type="button" className="btn ghost small" aria-label={`Remove ${p.label}`} disabled={busy}
                  onClick={() => setPeople((list) => list.filter((x) => x.id !== p.id))}>×</button>
              </li>
            ))}
          </ul>
        )}
        <SearchableSelect key={pickerKey} id="event-participant" label="Add an employee" noun="employee" search={employeeOptions}
          disabled={busy || people.length >= EVENT_LIMITS.employees}
          onChange={(option) => {
            if (option && !people.some((p) => p.id === option.id)) setPeople((list) => [...list, option]);
            if (option) setPickerKey((k) => k + 1);
          }} />
        {fieldError("participant_user_ids")}
      </fieldset>
      {field("notes", (
        <textarea id="event-notes" rows={3} maxLength={EVENT_LIMITS.notes} value={draft.notes} disabled={busy} onChange={(e) => set("notes", e.target.value)} {...a11y("notes")} />
      ))}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : event ? "Save event" : "Add event"}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={() => router.push(event ? eventPath(event.id) : CALENDAR_PATH)}>Cancel</button>
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </form>
  );
}
