"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import AgentShortlistUniversityPicker from "./AgentShortlistUniversityPicker";
import { NOT_COMPLETED } from "@/lib/apiErrors";
import {
  type AgentUniversity, buildEntryPayload, CATALOGUE_URL, type CatalogueCourse, changedOnly, COUNTRIES_URL, draftFromEntry, emptyEntryDraft,
  type EntryDraft, failureText, LIMITS, parseUniversityKey, type ShortlistEntry, shortlistUrl, UNIVERSITIES_URL, validateEntryDraft,
} from "@/lib/agentShortlist";
import type { Country, University } from "@/lib/types";

// AGN-007 (DEC-SCOPE-049 D4/D6): one shortlist entry. The university is a catalogue one or the agency's own; a catalogue course is offered
// only under its own catalogue university, otherwise the course is typed. Picking a course pre-fills intake, fee and requirements but
// never overwrites what the user typed. The server re-checks every rule (spec §5.4).
type Options = { catalogue: University[]; countries: Map<string, string>; agency: AgentUniversity[] };
type Static = Pick<Options, "catalogue" | "countries">;
// Only the static catalogue + countries are cached; the agency list changes (Master edits), so it is fetched on every mount.
let staticCache: Promise<Static> | null = null;
export function resetCatalogueCache() {
  staticCache = null;
}
async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}
function loadStatic(): Promise<Static> {
  staticCache ??= Promise.all([json<University[]>(CATALOGUE_URL), json<Country[]>(COUNTRIES_URL)])
    .then(([catalogue, countries]) => ({ catalogue, countries: new Map(countries.map((c) => [c.id, c.name])) }))
    .catch((error) => {
      staticCache = null; // a failed load is retried, not cached
      throw error;
    });
  return staticCache;
}
// The approved cap is 500 agency universities (spec §5): page by offset, 100 at a time, until total (at most 5 requests).
async function loadAgency(): Promise<AgentUniversity[]> {
  const items: AgentUniversity[] = [];
  for (let page = 0; page < 5; page++) {
    const body = await json<{ items: AgentUniversity[]; total?: number }>(`${UNIVERSITIES_URL}?limit=100&offset=${items.length}`);
    items.push(...body.items);
    if (body.items.length === 0 || items.length >= (body.total ?? 0)) break;
  }
  return items;
}
async function loadOptions(): Promise<Options> {
  const [stat, agency] = await Promise.all([loadStatic(), loadAgency()]);
  return { ...stat, agency };
}
const OTHER = "__other__";
const ENTRY_NOT_FOUND = "Shortlist entry not found";
type Field = "intake" | "tuitionFee" | "entryRequirements";

export default function AgentShortlistForm(props: { studentId: string; mode: "add" | "edit"; entry?: ShortlistEntry; onCancel: () => void; onSaved: (e: ShortlistEntry) => void; onGone: () => void; onEntryGone: () => void; onConflict: () => void }) {
  const { studentId, mode, entry, onCancel, onSaved, onGone, onEntryGone, onConflict } = props;
  const idPrefix = `sl-${useId().replace(/:/g, "")}`;
  const [options, setOptions] = useState<Options | null>(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [draft, setDraft] = useState<EntryDraft>(() => (entry ? draftFromEntry(entry) : emptyEntryDraft()));
  const [courses, setCourses] = useState<CatalogueCourse[] | null>(null);
  const [typedCourse, setTypedCourse] = useState(Boolean(entry?.course && !entry.course.id));
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // browser QA-01: Save is aria-disabled (a disabled button drops keyboard focus), so guard here
  const [failure, setFailure] = useState<string | null>(null);
  const touched = useRef(new Set<Field>(entry ? ["intake", "tuitionFee", "entryRequirements"] : []));
  const prefilled = useRef(new Set<Field>());
  const courseTicket = useRef(0);
  const choice = parseUniversityKey(draft.university);
  const catalogueUni = choice?.source === "catalogue" ? options?.catalogue.find((u) => u.id === choice.id) : undefined;
  const agencyUni = choice?.source === "agency" ? options?.agency.find((u) => u.id === choice.id) : undefined;
  const country = catalogueUni ? options?.countries.get(catalogueUni.country_id) : agencyUni?.country;

  const retryOptions = () => {
    setOptionsFailed(false);
    loadOptions().then(setOptions, () => setOptionsFailed(true));
  };
  useEffect(retryOptions, []);
  useEffect(() => document.getElementById(`${idPrefix}-title`)?.focus(), [idPrefix]);

  // A catalogue university's courses; a reply for an earlier choice is dropped (the openDetail ticket pattern).
  useEffect(() => {
    setCourses(null);
    const ticket = ++courseTicket.current;
    if (!catalogueUni) return;
    json<{ courses: CatalogueCourse[] }>(`${CATALOGUE_URL}/${catalogueUni.slug}`)
      .then((d) => ticket === courseTicket.current && setCourses(d.courses))
      .catch(() => ticket === courseTicket.current && setCourses([]));
  }, [catalogueUni]);

  const prefill = (values: Partial<Record<Field, string>>) => {
    const applied = Object.entries(values).filter(([k, v]) => v && !touched.current.has(k as Field));
    applied.forEach(([k]) => prefilled.current.add(k as Field));
    setDraft((d) => ({ ...d, ...Object.fromEntries(applied) }));
  };
  const type = (field: Field, value: string) => {
    touched.current.add(field);
    prefilled.current.delete(field); // typed over a prefill: now the user's value
    setDraft((d) => ({ ...d, [field]: value }));
  };

  function chooseUniversity(key: string) {
    const stale = [...prefilled.current]; // the old university's prefill must not linger; typed values stay
    prefilled.current.clear();
    setDraft((d) => ({ ...d, ...Object.fromEntries(stale.map((f) => [f, ""])), university: key, courseId: "", courseTitle: "" }));
    setTypedCourse(false);
    const picked = parseUniversityKey(key);
    if (picked?.source === "agency") prefill({ entryRequirements: options?.agency.find((u) => u.id === picked.id)?.entry_requirements ?? "" });
  }
  function chooseCourse(value: string) {
    if (value === OTHER) return (setTypedCourse(true), setDraft((d) => ({ ...d, courseId: "" })));
    setTypedCourse(false);
    setDraft((d) => ({ ...d, courseId: value, courseTitle: "" }));
    const course = courses?.find((c) => c.id === value);
    if (course) prefill({ intake: course.intake, tuitionFee: course.tuition_fee, entryRequirements: (catalogueUni?.requirements ?? []).join("\n") });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const problem = validateEntryDraft(draft);
    if (problem) return setFailure(problem);
    const payload = buildEntryPayload(draft);
    const body = entry ? changedOnly(payload, buildEntryPayload(draftFromEntry(entry))) : payload;
    if (entry && Object.keys(body).length === 0) return onCancel(); // nothing changed: no request
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(entry ? `${shortlistUrl(studentId)}/${entry.id}` : shortlistUrl(studentId), {
        method: entry ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.entry) return onSaved(data.entry);
      if (response.status === 404) return data?.detail === ENTRY_NOT_FOUND ? onEntryGone() : onGone(); // only the entry is gone: the student stays
      if (response.status === 409) return onConflict();
      setFailure(failureText(response.status, data?.detail, "Unable to save the shortlist entry."));
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation(); // the detail panel closes on Escape too; only the form closes here (Review Focus 4), never mid-save
      if (!busy) onCancel();
    }
  }

  const field = (key: Field, label: string, limit: number, multiline = false) => (
    <div className="field">
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      {multiline ? (
        <textarea id={`${idPrefix}-${key}`} rows={3} maxLength={limit} value={draft[key]} onChange={(e) => type(key, e.target.value)} />
      ) : (
        <input id={`${idPrefix}-${key}`} maxLength={limit} value={draft[key]} onChange={(e) => type(key, e.target.value)} />
      )}
    </div>
  );

  return (
    <form className="form card" onSubmit={submit} onKeyDown={onKeyDown} aria-busy={busy} noValidate aria-label={mode === "add" ? "Add to shortlist" : "Edit shortlist entry"}>
      {/* Browser QA-07: the h6 level stays (inside the h5 section); the size is not smaller than body text. */}
      <h6 id={`${idPrefix}-title`} tabIndex={-1} style={{ fontSize: "16px", margin: "0 0 8px" }}>{mode === "add" ? "Add a university" : `Edit ${entry?.university.name}`}</h6>
      <AgentShortlistUniversityPicker
        idPrefix={idPrefix}
        catalogue={options?.catalogue ?? null}
        countries={options?.countries ?? null}
        agency={options?.agency ?? null}
        value={draft.university}
        onChoose={chooseUniversity}
      />
      {optionsFailed && (
        <p className="form-error" role="alert">
          Unable to load universities.{" "}
          <button type="button" className="btn secondary small" onClick={retryOptions}>Retry</button>
        </p>
      )}
      {country && <p className="muted">Country: <span>{country}</span></p>}
      {catalogueUni && courses && (
        <div className="field">
          <label htmlFor={`${idPrefix}-course`}>Course</label>
          <select id={`${idPrefix}-course`} value={typedCourse ? OTHER : draft.courseId} onChange={(e) => chooseCourse(e.target.value)}>
            <option value="">— No course —</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            <option value={OTHER}>Other (type a course)</option>
          </select>
        </div>
      )}
      {(agencyUni || typedCourse) && (
        <div className="field">
          <label htmlFor={`${idPrefix}-course-title`}>{agencyUni ? "Course" : "Course name"}</label>
          <input id={`${idPrefix}-course-title`} maxLength={LIMITS.course_title} value={draft.courseTitle} onChange={(e) => setDraft((d) => ({ ...d, courseTitle: e.target.value }))} />
        </div>
      )}
      {field("intake", "Intake", LIMITS.intake)}
      {field("tuitionFee", "Tuition fee", LIMITS.tuition_fee)}
      {field("entryRequirements", "Entry requirements", LIMITS.entry_requirements, true)}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <button type="submit" className="btn small" aria-disabled={busy}>{busy ? "Saving…" : "Save to shortlist"}</button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  );
}
