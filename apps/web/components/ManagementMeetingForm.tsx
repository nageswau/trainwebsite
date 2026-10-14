"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { isoToIstInput, istInputToIso } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { roleLabel, type DiscussionOptions } from "@/lib/managementDiscussions";
import { KIND_LABEL, MEETINGS_API, MEETINGS_HOME, MODES, type MeetingDetail, type MeetingKind, type MeetingMode } from "@/lib/managementMeetings";
import { useHydrated } from "@/lib/useHydrated";

type Values = {
  title: string; kind: MeetingKind; starts_at: string; mode: MeetingMode; location: string; meeting_url: string; agenda: string; participant_ids: string[];
};
type Field = keyof Values;

function initial(meeting: MeetingDetail | undefined): Values {
  if (!meeting) return { title: "", kind: "partner", starts_at: "", mode: "Online", location: "", meeting_url: "", agenda: "", participant_ids: [] };
  return {
    title: meeting.title, kind: meeting.kind, starts_at: isoToIstInput(meeting.starts_at), mode: meeting.mode, location: meeting.location ?? "",
    meeting_url: meeting.meeting_url ?? "", agenda: meeting.agenda ?? "", participant_ids: meeting.participants.map((p) => p.id),
  };
}

/** The body the API takes: the IST start with its offset, optional text as null when blank. */
function body(values: Values): Record<string, unknown> {
  const blank = (value: string) => (value.trim() ? value.trim() : null);
  return {
    title: values.title.trim(), kind: values.kind, starts_at: values.starts_at ? istInputToIso(values.starts_at) : null, mode: values.mode,
    location: blank(values.location), meeting_url: blank(values.meeting_url), agenda: blank(values.agenda),
    participant_ids: [...values.participant_ids].sort(), // sorted, so an edit compares sets
  };
}

/** What the browser can check before sending; the API checks everything again (active staff, the time window). */
function validate(values: Values): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  const length = values.title.trim().length;
  if (length < 2 || length > 200) errors.title = "Give the title (2-200 characters)";
  if (!values.starts_at) errors.starts_at = "Choose the date and time";
  if (values.meeting_url.trim() && !/^https?:\/\//i.test(values.meeting_url.trim())) errors.meeting_url = "Use a link starting with http:// or https://";
  return errors;
}

// mgmt-029 (MM2-MM5): schedule a meeting or change one. An edit sends only the fields that changed, so nothing unchanged is
// re-recorded in the audit trail or re-announced to the participants. Minutes, decisions and tasks are added on the meeting's page.
export default function ManagementMeetingForm({ options, meeting }: { options: DiscussionOptions; meeting?: MeetingDetail }) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Values>(() => initial(meeting));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // a second click before the re-render disables the form is ignored
  const [search, setSearch] = useState("");
  const set = (key: Field, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => Object.fromEntries(Object.entries(e).filter(([field]) => field !== key))); // a changed field drops its old error
  };

  // A participant who has since left still shows, so the current list is never silently dropped.
  const people = [...options.users];
  for (const p of meeting?.participants ?? []) if (!people.some((u) => u.id === p.id)) people.push(p);
  const shown = people.filter((p) => values.participant_ids.includes(p.id) || p.full_name.toLowerCase().includes(search.trim().toLowerCase()));
  const toggle = (id: string) => setValues((v) => ({ ...v, participant_ids: v.participant_ids.includes(id) ? v.participant_ids.filter((x) => x !== id) : [...v.participant_ids, id] }));

  const fieldProps = (key: Field) => ({ id: `meeting-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `meeting-${key}-error` : undefined });
  const error = (key: Field) => errors[key] && <p className="form-error" id={`meeting-${key}-error`}>{errors[key]}</p>;

  async function save() {
    if (sending.current) return;
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage("Check the highlighted fields.");
      document.getElementById(`meeting-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    let payload = body(values);
    if (meeting) {
      const before = body(initial(meeting));
      payload = Object.fromEntries(Object.entries(payload).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(before[key])));
      if (Object.keys(payload).length === 0) {
        router.push(`${MEETINGS_HOME}/${meeting.id}`);
        return;
      }
    }
    sending.current = true;
    setBusy(true);
    setMessage("");
    const saved = meeting ? await sendJson(`${MEETINGS_API}/${meeting.id}`, "PATCH", payload) : await sendJson(MEETINGS_API, "POST", payload);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? "Check the highlighted fields." : saved.message);
      sending.current = false;
      setBusy(false);
      return;
    }
    router.push(`${MEETINGS_HOME}/${meeting?.id ?? String(saved.data.id)}`);
    router.refresh(); // the meeting page may be cached from before this change
  }

  return (
    <form className="form action-card" noValidate aria-label={meeting ? "Edit meeting" : "New meeting"} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="field">
          <label htmlFor="meeting-title">Title</label>
          <input type="text" maxLength={200} value={values.title} onChange={(e) => set("title", e.target.value)} {...fieldProps("title")} />
          {error("title")}
        </div>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="meeting-kind">Kind</label>
            <select value={values.kind} onChange={(e) => set("kind", e.target.value)} {...fieldProps("kind")}>
              {Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {error("kind")}
          </div>
          <div className="field">
            <label htmlFor="meeting-starts_at">Date and time (IST)</label>
            <input type="datetime-local" value={values.starts_at} onChange={(e) => set("starts_at", e.target.value)} {...fieldProps("starts_at")} />
            {error("starts_at")}
          </div>
          <div className="field">
            <label htmlFor="meeting-mode">Mode</label>
            <select value={values.mode} onChange={(e) => set("mode", e.target.value)} {...fieldProps("mode")}>
              {MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
            </select>
            {error("mode")}
          </div>
          <div className="field">
            <label htmlFor="meeting-location">Location (optional)</label>
            <input type="text" maxLength={200} value={values.location} onChange={(e) => set("location", e.target.value)} {...fieldProps("location")} />
            {error("location")}
          </div>
        </div>
        <div className="field">
          <label htmlFor="meeting-meeting_url">Meeting link (optional)</label>
          <input type="url" inputMode="url" maxLength={500} placeholder="https://" value={values.meeting_url} onChange={(e) => set("meeting_url", e.target.value)} {...fieldProps("meeting_url")} />
          {error("meeting_url")}
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }} aria-describedby={errors.participant_ids ? "meeting-participant_ids-error" : undefined}>
          <legend style={{ fontWeight: 800, fontSize: 13, marginBottom: 7 }}>Participants (optional)</legend>
          <input type="search" aria-label="Find a participant" placeholder="Find by name" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 8 }} />
          <div style={{ maxHeight: 220, overflowY: "auto", display: "grid", gap: 6, padding: 4 }}>
            {shown.length === 0 && <span className="muted">No staff member matches.</span>}
            {shown.map((p) => (
              <label key={p.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={values.participant_ids.includes(p.id)} onChange={() => toggle(p.id)} />
                {p.full_name} ({roleLabel(p.role)})
              </label>
            ))}
          </div>
          {errors.participant_ids && <p className="form-error" id="meeting-participant_ids-error">{errors.participant_ids}</p>}
        </fieldset>
        <div className="field">
          <label htmlFor="meeting-agenda">Agenda (optional)</label>
          <textarea rows={4} maxLength={5000} value={values.agenda} onChange={(e) => set("agenda", e.target.value)} {...fieldProps("agenda")} />
          {error("agenda")}
        </div>
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>Participants are notified and see the time, place, link and agenda in their Management tasks page — never the minutes.</p>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : meeting ? "Save changes" : "Schedule meeting"}</button>
          <a className="btn ghost" href={meeting ? `${MEETINGS_HOME}/${meeting.id}` : MEETINGS_HOME}>Cancel</a>
        </div>
      </fieldset>
    </form>
  );
}
