"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import {
  CHECKLIST_DOCUMENT_TYPES,
  CHECKLISTS_URL,
  COURSE_LEVELS,
  DRAFTING_STATUSES,
  GATE_LABELS,
  KIND_LABELS,
  MAX_ITEMS,
  STANDARD_STATUSES,
  STATUS_LABELS,
  universitySearch,
  type ChecklistDocumentType,
  type ChecklistKind,
  type ChecklistTemplate,
  type CourseLevel,
  type GateMode,
  type ItemStatus,
} from "@/lib/documentChecklists";
import type { PickOption } from "@/lib/lookups";
import { countrySearch } from "@/lib/universities";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Row = { key: number; document_type: ChecklistDocumentType; label: string; required: boolean; allowed_statuses: ItemStatus[]; notes: string };
type Props = { template: ChecklistTemplate | null; onSaved: (saved: ChecklistTemplate) => void; onCancel: () => void };

const ALL_STATUSES: ItemStatus[] = [...STANDARD_STATUSES, ...DRAFTING_STATUSES];
let nextKey = 1;
const newRow = (): Row => ({ key: nextKey++, document_type: "Passport", label: "", required: true, allowed_statuses: [...STANDARD_STATUSES], notes: "" });

// ccrm-018 (DEC-SCOPE-248): create or edit one checklist template -- scope, gate mode (CC10) and the ordered items, each with its
// allowed statuses. An edit sends the version it loaded; the server answers 409 when another admin saved first or the scope is taken,
// and that message stays beside the form with the entry kept. Escape cancels.
export default function ChecklistTemplateEditor({ template, onSaved, onCancel }: Props) {
  const [name, setName] = useState(template?.name ?? "");
  const [kind, setKind] = useState<ChecklistKind>(template?.kind ?? "admission");
  const [country, setCountry] = useState<PickOption | null>(template ? { id: template.country_id, label: template.country_name ?? "" } : null);
  const [university, setUniversity] = useState<PickOption | null>(template?.university_id ? { id: template.university_id, label: template.university_name ?? "" } : null);
  const [level, setLevel] = useState<CourseLevel | "">(template?.course_level ?? "");
  const [intake, setIntake] = useState(template?.intake ?? "");
  const [gate, setGate] = useState<GateMode>(template?.gate_mode ?? "block");
  const [notes, setNotes] = useState(template?.notes ?? "");
  const [active, setActive] = useState(template?.active ?? true);
  const [rows, setRows] = useState<Row[]>(() =>
    template
      ? template.items.map((i) => ({ key: nextKey++, document_type: i.document_type, label: i.label ?? "", required: i.required, allowed_statuses: i.allowed_statuses, notes: i.notes ?? "" }))
      : [newRow()],
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inFlight = useRef(false);
  const focusAfter = useFocusAfterRender();
  const prefix = `checklist-${template?.id ?? "new"}`;
  const id = (part: string) => `${prefix}-${part}`;

  function update(key: number, patch: Partial<Row>) {
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function move(index: number, by: -1 | 1) {
    setRows((current) => {
      const next = [...current];
      [next[index], next[index + by]] = [next[index + by], next[index]];
      return next;
    });
    focusAfter(id(`item-${index + by}-${by < 0 ? "up" : "down"}`));
  }
  function toggleStatus(row: Row, status: ItemStatus) {
    const on = row.allowed_statuses.includes(status);
    update(row.key, { allowed_statuses: on ? row.allowed_statuses.filter((s) => s !== status) : ALL_STATUSES.filter((s) => s === status || row.allowed_statuses.includes(s)) });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !country) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    const body = {
      name,
      kind,
      country_id: country.id,
      university_id: university?.id ?? null,
      course_level: level || null,
      intake: intake.trim() || null,
      gate_mode: gate,
      notes: notes.trim() || null,
      items: rows.map((r) => ({ document_type: r.document_type, label: r.label.trim() || null, required: r.required, allowed_statuses: r.allowed_statuses, notes: r.notes.trim() || null })),
      ...(template ? { version: template.version, active } : {}),
    };
    const outcome = await sendJson(template ? `${CHECKLISTS_URL}/${template.id}` : CHECKLISTS_URL, template ? "PUT" : "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setFailure(outcome.message);
      return focusAfter(id("failure"));
    }
    onSaved(outcome.data as ChecklistTemplate);
  }

  const title = template ? `Edit ${template.name}` : "New checklist template";
  return (
    <form className="form" aria-label={title} onSubmit={submit} onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && onCancel()}>
      <h4>{title}</h4>
      <p className="muted" style={{ fontSize: 13 }}>
        A template applies only to applications that match its scope. The most specific match wins: a university template overrides a course-level one, which
        overrides an intake one.
      </p>
      <div className="grid two">
        <div className="field">
          <label htmlFor={id("name")}>Name</label>
          <input id={id("name")} required maxLength={120} autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        <div className="field">
          <label htmlFor={id("kind")}>Checklist for</label>
          <select id={id("kind")} value={kind} onChange={(e) => setKind(e.target.value as ChecklistKind)}>
            {(Object.keys(KIND_LABELS) as ChecklistKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <SearchableSelect
            label="Country"
            noun="country"
            id={id("country")}
            required
            search={countrySearch}
            initial={country}
            onChange={(option) => {
              setCountry(option);
              setUniversity(null);
            }}
          />
        </div>
        <div className="field">
          {country ? (
            <SearchableSelect key={country.id} label="University (optional)" noun="university" id={id("university")} search={universitySearch(country.id)} initial={university} onChange={setUniversity} />
          ) : (
            <>
              <label htmlFor={id("university-off")}>University (optional)</label>
              <input id={id("university-off")} disabled placeholder="Choose a country first" />
            </>
          )}
        </div>
        <div className="field">
          <label htmlFor={id("level")}>Course level (optional)</label>
          <select id={id("level")} value={level} onChange={(e) => setLevel(e.target.value as CourseLevel | "")}>
            <option value="">Any level</option>
            {COURSE_LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={id("intake")}>Intake (optional)</label>
          <input id={id("intake")} maxLength={80} autoComplete="off" placeholder="e.g. September 2027" value={intake} onChange={(e) => setIntake(e.target.value)} />
        </div>
      </div>
      <fieldset className="field">
        <legend>When documents are missing at Ready for Submission</legend>
        {(Object.keys(GATE_LABELS) as GateMode[]).map((g) => (
          <label key={g} style={{ display: "block" }}>
            <input type="radio" name={id("gate")} value={g} checked={gate === g} onChange={() => setGate(g)} /> {GATE_LABELS[g]}
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor={id("notes")}>Notes (optional)</label>
        <textarea id={id("notes")} maxLength={2000} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      {template && (
        <label style={{ display: "block", marginBottom: 12 }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active (inactive templates never apply)
        </label>
      )}
      <fieldset className="field">
        <legend>Documents ({rows.length})</legend>
        <ol style={{ paddingLeft: 20, display: "grid", gap: 12 }}>
          {rows.map((row, index) => (
            <li key={row.key} className="card" aria-label={`Document ${index + 1}`}>
              <div className="grid two">
                <div className="field">
                  <label htmlFor={id(`item-${row.key}-type`)}>Document type</label>
                  <select id={id(`item-${row.key}-type`)} value={row.document_type} onChange={(e) => update(row.key, { document_type: e.target.value as ChecklistDocumentType })}>
                    {CHECKLIST_DOCUMENT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor={id(`item-${row.key}-label`)}>{row.document_type === "Other" ? "Document name" : "Label (optional)"}</label>
                  <input
                    id={id(`item-${row.key}-label`)}
                    maxLength={80}
                    autoComplete="off"
                    required={row.document_type === "Other"}
                    value={row.label}
                    onChange={(e) => update(row.key, { label: e.target.value })}
                  />
                </div>
              </div>
              <label style={{ display: "block" }}>
                <input type="checkbox" checked={row.required} onChange={(e) => update(row.key, { required: e.target.checked })} /> Required
              </label>
              <fieldset style={{ border: 0, padding: 0, margin: "8px 0" }}>
                <legend style={{ fontSize: 13 }}>Allowed statuses (none ticked = the standard nine)</legend>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
                  {ALL_STATUSES.map((s) => (
                    <label key={s} style={{ fontSize: 13 }}>
                      <input type="checkbox" checked={row.allowed_statuses.includes(s)} onChange={() => toggleStatus(row, s)} /> {STATUS_LABELS[s]}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="field">
                <label htmlFor={id(`item-${row.key}-notes`)}>Item notes (optional)</label>
                <input id={id(`item-${row.key}-notes`)} maxLength={1000} autoComplete="off" value={row.notes} onChange={(e) => update(row.key, { notes: e.target.value })} />
              </div>
              <div className="actions">
                <button type="button" id={id(`item-${index}-up`)} className="btn ghost small" disabled={index === 0} aria-label={`Move document ${index + 1} up`} onClick={() => move(index, -1)}>
                  Move up
                </button>
                <button
                  type="button"
                  id={id(`item-${index}-down`)}
                  className="btn ghost small"
                  disabled={index === rows.length - 1}
                  aria-label={`Move document ${index + 1} down`}
                  onClick={() => move(index, 1)}
                >
                  Move down
                </button>
                <button
                  type="button"
                  className="btn ghost small"
                  disabled={rows.length === 1}
                  aria-label={`Remove document ${index + 1}`}
                  onClick={() => {
                    setRows((current) => current.filter((r) => r.key !== row.key));
                    focusAfter(id("add"));
                  }}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ol>
        <button type="button" id={id("add")} className="btn secondary small" disabled={rows.length >= MAX_ITEMS} onClick={() => setRows((current) => [...current, newRow()])}>
          Add document
        </button>
      </fieldset>
      {failure && (
        <p id={id("failure")} tabIndex={-1} className="form-error" role="alert">
          {failure}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !country}>
          {busy ? "Saving…" : template ? "Save changes" : "Create template"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
