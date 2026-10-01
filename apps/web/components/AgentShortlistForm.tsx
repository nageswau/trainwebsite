"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import {
  type AgentUniversity, buildEntryPayload, CATALOGUE_URL, type CatalogueCourse, changedOnly, COUNTRIES_URL, draftFromEntry, emptyEntryDraft,
  type EntryDraft, LIMITS, parseUniversityKey, type ShortlistEntry, shortlistUrl, UNIVERSITIES_URL, validateEntryDraft,
} from "@/lib/agentShortlist";
import type { Country, University } from "@/lib/types";

// AGN-007 (DEC-SCOPE-049 D4/D6): one shortlist entry. The university is a catalogue one or the agency's own; a catalogue course is offered
// only under its own catalogue university, otherwise the course is typed. Picking a course pre-fills intake, fee and requirements but
// never overwrites what the user typed. The server re-checks every rule (spec §5.4).
type Options = { catalogue: University[]; countries: Map<string, string>; agency: AgentUniversity[] };
let catalogueCache: Promise<Options> | null = null;
export function resetCatalogueCache() {
  catalogueCache = null;
}
async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}
function loadOptions(): Promise<Options> {
  catalogueCache ??= Promise.all([json<University[]>(CATALOGUE_URL), json<Country[]>(COUNTRIES_URL), json<{ items: AgentUniversity[] }>(`${UNIVERSITIES_URL}?limit=100`)])
    .then(([catalogue, countries, agency]) => ({ catalogue, countries: new Map(countries.map((c) => [c.id, c.name])), agency: agency.items }))
    .catch((error) => {
      catalogueCache = null; // a failed load is retried, not cached
      throw error;
    });
  return catalogueCache;
}
const OTHER = "__other__";
type Field = "intake" | "tuitionFee" | "entryRequirements";

export default function AgentShortlistForm(props: { studentId: string; mode: "add" | "edit"; entry?: ShortlistEntry; onCancel: () => void; onSaved: (e: ShortlistEntry) => void; onGone: () => void; onConflict: () => void }) {
  const { studentId, mode, entry, onCancel, onSaved, onGone, onConflict } = props;
  const idPrefix = `sl-${useId().replace(/:/g, "")}`;
  const [options, setOptions] = useState<Options | null>(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [draft, setDraft] = useState<EntryDraft>(() => (entry ? draftFromEntry(entry) : emptyEntryDraft()));
  const [courses, setCourses] = useState<CatalogueCourse[] | null>(null);
  const [typedCourse, setTypedCourse] = useState(Boolean(entry?.course && !entry.course.id));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const touched = useRef(new Set<Field>(entry ? ["intake", "tuitionFee", "entryRequirements"] : []));
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

  const prefill = (values: Partial<Record<Field, string>>) =>
    setDraft((d) => ({ ...d, ...Object.fromEntries(Object.entries(values).filter(([k, v]) => v && !touched.current.has(k as Field))) }));
  const type = (field: Field, value: string) => {
    touched.current.add(field);
    setDraft((d) => ({ ...d, [field]: value }));
  };

  function chooseUniversity(key: string) {
    setDraft((d) => ({ ...d, university: key, courseId: "", courseTitle: "" }));
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
    const problem = validateEntryDraft(draft);
    if (problem) return setFailure(problem);
    const payload = buildEntryPayload(draft);
    const body = entry ? changedOnly(payload, buildEntryPayload(draftFromEntry(entry))) : payload;
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
      if (response.status === 404) return onGone();
      if (response.status === 409) return onConflict();
      setFailure(detailMessage(data?.detail, "Unable to save the shortlist entry."));
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation(); // the detail panel closes on Escape too; only the form closes here (Review Focus 4)
      onCancel();
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
      <h6 id={`${idPrefix}-title`} tabIndex={-1}>{mode === "add" ? "Add a university" : `Edit ${entry?.university.name}`}</h6>
      <div className="field">
        <label htmlFor={`${idPrefix}-uni`}>University (required)</label>
        <select id={`${idPrefix}-uni`} value={draft.university} disabled={!options} aria-required="true" onChange={(e) => chooseUniversity(e.target.value)}>
          <option value="">{options ? "— Choose a university —" : "Loading universities…"}</option>
          {options && (
            <optgroup label="Catalogue">
              {options.catalogue.map((u) => <option key={u.id} value={`c:${u.id}`}>{`${u.name} — ${u.city}`}</option>)}
            </optgroup>
          )}
          {options && options.agency.length > 0 && (
            <optgroup label="Your agency">
              {options.agency.map((u) => <option key={u.id} value={`a:${u.id}`}>{`${u.name} — ${u.country}`}</option>)}
            </optgroup>
          )}
        </select>
      </div>
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
      <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save to shortlist"}</button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  );
}
