"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import type { PickOption } from "@/lib/lookups";
import { contactsUrl } from "@/lib/universities";
import { employeeOptions, indiaToday, leadOptions, universityOptions, type Visit, VISITS_URL, visitPath, visitUrl } from "@/lib/visits";

// upc-010 (§8): plan a visit, or edit one. On edit only the fields the API lists in `editable_fields` are enabled (VS9: the approved plan
// is locked) and only what changed is sent. The meeting contacts are the visited university's (upc-006), loaded once it is known.
const TEXT = ["purpose", "city", "travel_notes", "hotel_notes", "agenda", "expected_outcome"] as const;
const DATES = ["proposed_date", "confirmed_date", "follow_up_date"] as const;
type Draft = Record<(typeof TEXT)[number] | (typeof DATES)[number], string> & { travel_required: boolean; hotel_required: boolean };

const LABELS: Record<string, string> = {
  purpose: "Visit purpose (required)", city: "City", travel_notes: "Travel notes", hotel_notes: "Hotel notes", agenda: "Agenda",
  expected_outcome: "Expected outcome", proposed_date: "Proposed visit date (required)", confirmed_date: "Confirmed visit date",
  follow_up_date: "Follow-up date", university_id: "University", lead_user_id: "Lead (partnership manager)",
  participant_user_ids: "Other EduSphere employees", contact_ids: "Meeting contacts",
};
const LIMITS: Record<string, number> = { purpose: 1000, city: 120, travel_notes: 1000, hotel_notes: 1000, agenda: 2000, expected_outcome: 2000 };
const MULTILINE = new Set(["purpose", "travel_notes", "hotel_notes", "agenda", "expected_outcome"]);
const SAVE_FAILED = "The visit could not be saved. Try again.";

const draftOf = (v?: Visit): Draft => ({
  purpose: v?.purpose ?? "", city: v?.city ?? "", travel_notes: v?.travel_notes ?? "", hotel_notes: v?.hotel_notes ?? "", agenda: v?.agenda ?? "",
  expected_outcome: v?.expected_outcome ?? "", proposed_date: v?.proposed_date ?? "", confirmed_date: v?.confirmed_date ?? "",
  follow_up_date: v?.follow_up_date ?? "", travel_required: v?.travel_required ?? false, hotel_required: v?.hotel_required ?? false,
});
const person = (p: { id: string; full_name: string }): PickOption => ({ id: p.id, label: p.full_name });
const sameIds = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join() === [...b].sort().join();

type Contact = { id: string; name: string; designation: string | null };

export default function VisitForm({ visit, university, canPickLead }: { visit?: Visit; university?: PickOption | null; canPickLead: boolean }) {
  const router = useRouter();
  const sending = useRef(false);
  const [draft, setDraft] = useState(() => draftOf(visit));
  const [uni, setUni] = useState<PickOption | null>(visit ? { id: visit.university.id, label: visit.university.name } : university ?? null);
  const [lead, setLead] = useState<PickOption | null>(visit && canPickLead ? person(visit.lead) : null);
  const [people, setPeople] = useState<PickOption[]>(() => (visit?.participants ?? []).map(person));
  const [pickerKey, setPickerKey] = useState(0);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [chosen, setChosen] = useState<string[]>(() => (visit?.contacts ?? []).map((c) => c.id));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const enabled = (name: string) => !visit || visit.editable_fields.includes(name);
  const fixedUniversity = Boolean(visit || university);

  useEffect(() => {
    if (!uni) return setContacts(null);
    const controller = new AbortController();
    fetch(`${contactsUrl(uni.id)}?limit=50`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setContacts(isPage<Contact>(data) ? data.items : []))
      .catch(() => controller.signal.aborted || setContacts([]));
    return () => controller.abort();
  }, [uni]);

  const set = (name: keyof Draft, value: string | boolean) => setDraft((d) => ({ ...d, [name]: value }));
  const a11y = (name: string) => (errors[name] ? { "aria-invalid": true as const, "aria-describedby": `visit-${name}-error` } : {});
  const field = (name: string, control: ReactNode) => (
    <div className="field" key={name}>
      <label htmlFor={`visit-${name}`}>{LABELS[name]}</label>
      {control}
      {errors[name] && <p className="field-error" id={`visit-${name}-error`} style={{ color: "var(--red)", fontSize: 13, margin: "4px 0 0" }}>{errors[name]}</p>}
    </div>
  );

  function body(): Record<string, unknown> {
    if (!visit) {
      const out: Record<string, unknown> = { university_id: uni?.id, purpose: draft.purpose.trim(), proposed_date: draft.proposed_date, travel_required: draft.travel_required, hotel_required: draft.hotel_required };
      for (const key of [...TEXT, ...DATES]) if (!(key in out) && draft[key].trim()) out[key] = draft[key].trim();
      if (lead) out.lead_user_id = lead.id;
      return { ...out, participant_user_ids: people.map((p) => p.id), contact_ids: chosen };
    }
    const base = draftOf(visit);
    const out: Record<string, unknown> = {};
    for (const key of [...TEXT, ...DATES]) if (draft[key].trim() !== base[key].trim()) out[key] = draft[key].trim() || null;
    for (const key of ["travel_required", "hotel_required"] as const) if (draft[key] !== base[key]) out[key] = draft[key];
    if (canPickLead && lead && lead.id !== visit.lead.id) out.lead_user_id = lead.id;
    if (!sameIds(people.map((p) => p.id), visit.participants.map((p) => p.id))) out.participant_user_ids = people.map((p) => p.id);
    if (!sameIds(chosen, visit.contacts.map((c) => c.id))) out.contact_ids = chosen;
    return out;
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const missing: Record<string, string> = {};
    if (!uni) missing.university_id = "Choose a university";
    if (!draft.purpose.trim()) missing.purpose = "Visit purpose is required";
    if (!draft.proposed_date) missing.proposed_date = "Proposed visit date is required";
    setErrors(missing);
    setFailure(null);
    if (Object.keys(missing).length) return;
    const payload = body();
    if (visit && !Object.keys(payload).length) return router.push(visitPath(visit.id));
    sending.current = true;
    setBusy(true);
    const outcome = await sendJson(visit ? visitUrl(visit.id) : VISITS_URL, visit ? "PATCH" : "POST", payload);
    sending.current = false;
    setBusy(false);
    const saved = outcome.ok ? (outcome.data.visit as { id?: string } | undefined) : undefined;
    if (saved?.id) return router.push(visitPath(saved.id));
    if (outcome.ok) return setFailure(SAVE_FAILED);
    const mapped = outcome.status === 422 ? fieldErrors(outcome.detail) : {};
    setErrors(mapped);
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const text = (name: (typeof TEXT)[number]) =>
    field(name, MULTILINE.has(name) ? (
      <textarea id={`visit-${name}`} rows={name === "purpose" ? 2 : 3} maxLength={LIMITS[name]} value={draft[name]} disabled={busy || !enabled(name)}
        onChange={(e) => set(name, e.target.value)} {...a11y(name)} />
    ) : (
      <input id={`visit-${name}`} maxLength={LIMITS[name]} value={draft[name]} disabled={busy || !enabled(name)} placeholder={name === "city" ? "The university's city" : undefined}
        onChange={(e) => set(name, e.target.value)} {...a11y(name)} />
    ));
  const date = (name: (typeof DATES)[number]) =>
    field(name, <input id={`visit-${name}`} type="date" min={indiaToday()} value={draft[name]} disabled={busy || !enabled(name)} onChange={(e) => set(name, e.target.value)} {...a11y(name)} />);
  const flag = (name: "travel_required" | "hotel_required", words: string) => (
    <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      <input type="checkbox" checked={draft[name]} disabled={busy || !enabled(name)} onChange={(e) => set(name, e.target.checked)} /> {words}
    </label>
  );

  return (
    <form onSubmit={save} noValidate aria-label={visit ? `Edit ${visit.code}` : "Plan a university visit"} style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {fixedUniversity ? (
          <div className="field">
            <span className="muted">University</span>
            <p style={{ margin: "4px 0 0", fontWeight: 700 }}>{uni?.label}</p>
            {university?.detail && <p className="muted" style={{ margin: 0 }}>{university.detail}</p>}
          </div>
        ) : (
          <div>
            <SearchableSelect id="visit-university_id" label="University" noun="university" search={universityOptions} disabled={busy}
              onChange={(option) => { setUni(option); setChosen([]); }} />
            {errors.university_id && <p className="field-error" style={{ color: "var(--red)", fontSize: 13, margin: "4px 0 0" }}>{errors.university_id}</p>}
          </div>
        )}
        {canPickLead && (
          <div>
            <SearchableSelect id="visit-lead_user_id" label={LABELS.lead_user_id} noun="manager" search={leadOptions} initial={lead}
              disabled={busy || !enabled("lead_user_id")} onChange={setLead} />
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>Leave empty to lead the visit yourself.</p>
            {errors.lead_user_id && <p className="field-error" style={{ color: "var(--red)", fontSize: 13, margin: "4px 0 0" }}>{errors.lead_user_id}</p>}
          </div>
        )}
        {text("city")}
        {date("proposed_date")}
        {date("confirmed_date")}
        {visit && enabled("follow_up_date") && date("follow_up_date")}
      </div>
      {text("purpose")}
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 12 }}>
        <legend>Travel and hotel</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          {flag("travel_required", "Travel required")}
          {flag("hotel_required", "Hotel required")}
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
          {text("travel_notes")}
          {text("hotel_notes")}
        </div>
      </fieldset>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 10 }}>
        <legend>{LABELS.participant_user_ids}</legend>
        {people.length > 0 && (
          <ul aria-label="Employees on the visit" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {people.map((p) => (
              <li key={p.id} className="badge" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                {p.label}
                {enabled("participant_user_ids") && (
                  <button type="button" className="btn ghost small" aria-label={`Remove ${p.label}`} disabled={busy}
                    onClick={() => setPeople((list) => list.filter((x) => x.id !== p.id))}>×</button>
                )}
              </li>
            ))}
          </ul>
        )}
        {enabled("participant_user_ids") && (
          <SearchableSelect key={pickerKey} id="visit-participant" label="Add an employee" noun="employee" search={employeeOptions} disabled={busy || people.length >= 10}
            onChange={(option) => {
              if (option && !people.some((p) => p.id === option.id)) setPeople((list) => [...list, option]);
              if (option) setPickerKey((k) => k + 1);
            }} />
        )}
        {errors.participant_user_ids && <p className="field-error" style={{ color: "var(--red)", fontSize: 13, margin: 0 }}>{errors.participant_user_ids}</p>}
      </fieldset>
      <fieldset className="card" style={{ padding: 14, display: "grid", gap: 8 }} disabled={busy || !enabled("contact_ids")}>
        <legend>{LABELS.contact_ids}</legend>
        {!uni ? <p className="muted" style={{ margin: 0 }}>Choose the university first.</p>
          : contacts === null ? <p className="muted" style={{ margin: 0 }}>Loading contacts…</p>
          : contacts.length === 0 ? <p className="muted" style={{ margin: 0 }}>No contacts recorded for this university yet.</p>
          : contacts.map((c) => (
            <label key={c.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={chosen.includes(c.id)}
                onChange={(e) => setChosen((list) => (e.target.checked ? [...list, c.id] : list.filter((id) => id !== c.id)))} />
              {c.name}{c.designation ? ` — ${c.designation}` : ""}
            </label>
          ))}
        {errors.contact_ids && <p className="field-error" style={{ color: "var(--red)", fontSize: 13, margin: 0 }}>{errors.contact_ids}</p>}
      </fieldset>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {text("agenda")}
        {text("expected_outcome")}
      </div>
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save visit"}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={() => router.push(visit ? visitPath(visit.id) : "/partnership/visits")}>Cancel</button>
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </form>
  );
}
