"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { CAREER_LIST_FIELDS, type CareerRecord, type CareerStatus, RECORD_TYPE_LABEL, STRUCTURED_TYPES, statusLabel, statusOptions } from "@/lib/careerRecords";
import { listText, splitList } from "@/lib/schoolStudents";

type Student = { id: string; full_name: string; school_name: string };

/** An ISO timestamp as the browser-local value a datetime-local input expects ("YYYY-MM-DDTHH:mm"). */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const yesNo = (value: boolean | null | undefined) => (value === true ? "yes" : value === false ? "no" : "");

/** Today as a date input value, so the picker never offers a past follow-up date (QA-03; the server still decides). */
function todayInput(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ENH-026: create and edit one counselling record. Groups follow spec §11.2 F1; the status select only ever offers states the
// API will accept (F3), so a refused save usually means someone else changed the record -- shown with a Reload action (F7).
export default function CareerRecordForm({ students, record, onDone, onCancel }: { students: Student[]; record?: CareerRecord; onDone: () => void; onCancel: () => void }) {
  const router = useRouter();
  const editing = Boolean(record);
  const [recordType, setRecordType] = useState(record?.record_type ?? "");
  const [status, setStatus] = useState<CareerStatus | "">(record?.status ?? (editing ? "" : "completed"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const structured = STRUCTURED_TYPES.includes(recordType);
  const prefix = record ? `career-${record.id}` : "career-new";

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  function payload(form: FormData): Record<string, unknown> {
    const body: Record<string, unknown> = { notes: String(form.get("notes") ?? "") };
    if (!editing) Object.assign(body, { school_student_id: form.get("school_student_id"), record_type: recordType });
    if (editing) body.expected_status = record?.status ?? null;
    if (!structured) return body;
    if (status) body.status = status;
    const scheduled = String(form.get("scheduled_for") ?? "");
    if (scheduled) body.scheduled_for = new Date(scheduled).toISOString();
    for (const key of ["completed_on", "next_follow_up_date"]) {
      const value = String(form.get(key) ?? "");
      if (value) body[key] = value;
    }
    for (const field of CAREER_LIST_FIELDS) {
      const items = splitList(form.get(field.key));
      if (items.length || editing) body[field.key] = items.length ? items : null;
    }
    for (const key of ["global_education_interest", "parent_participated"]) {
      const value = String(form.get(key) ?? "");
      if (value || editing) body[key] = value === "" ? null : value === "yes";
    }
    const note = String(form.get("parent_participation_note") ?? "").trim();
    if (note || editing) body.parent_participation_note = note || null;
    return body;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    const formElement = event.currentTarget;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    setStale(false);
    const url = editing ? `/api/v1/school/career-counselor/records/${record!.id}` : "/api/v1/school/career-counselor/records";
    // Raw fetch (the PortfolioEntryForm pattern) rather than sendJson: a 409 needs the status code to offer Reload (spec F7).
    let response: Response | null;
    try {
      response = await fetch(url, { method: editing ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload(new FormData(formElement))) });
    } catch {
      response = null;
    }
    const data = response ? await response.json().catch(() => null) : null;
    inFlight.current = false;
    setBusy(false);
    if (!response?.ok) {
      setStale(response?.status === 409);
      setMessage({ text: response ? detailMessage(data?.detail) : NOT_COMPLETED, failed: true });
      return;
    }
    setMessage({ text: "Record saved.", failed: false });
    if (!editing) formElement.reset();
    router.refresh();
    onDone();
  }

  return (
    <form className="form" onSubmit={submit} onKeyDown={onKey}>
      <fieldset className="form-busy-wrap" disabled={busy}>
        {!editing && (
          <>
            <div className="field">
              <label htmlFor={`${prefix}-student`}>Student</label>
              <select id={`${prefix}-student`} name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-type`}>Type</label>
              <select id={`${prefix}-type`} name="record_type" required value={recordType} onChange={(e) => setRecordType(e.target.value)}>
                <option value="" disabled>Select type</option>
                {Object.entries(RECORD_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
          </>
        )}
        {structured && (
          <fieldset className="form-section">
            <legend>Session</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor={`${prefix}-status`}>Status</label>
                <select id={`${prefix}-status`} value={status} onChange={(e) => setStatus(e.target.value as CareerStatus)} aria-describedby={`${prefix}-status-help`}>
                  {editing && !record?.status && <option value="">{statusLabel(null)}</option>}
                  {statusOptions(record?.status, !editing).map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                </select>
                <p id={`${prefix}-status-help`} className="field-help muted">Not Started → Scheduled → Completed → Follow-up Required → Completed</p>
              </div>
              {status === "scheduled" && (
                <div className="field">
                  <label htmlFor={`${prefix}-scheduled`}>Scheduled for</label>
                  <input id={`${prefix}-scheduled`} name="scheduled_for" type="datetime-local" required defaultValue={record?.status === "scheduled" ? toLocalInput(record.scheduled_for) : ""} />
                </div>
              )}
              {status === "completed" && (
                <div className="field">
                  <label htmlFor={`${prefix}-completed`}>Completed on (defaults to today)</label>
                  <input id={`${prefix}-completed`} name="completed_on" type="date" defaultValue={record?.completed_on ?? ""} />
                </div>
              )}
              {status === "follow_up_required" && (
                <div className="field">
                  <label htmlFor={`${prefix}-follow`}>Next follow-up</label>
                  <input id={`${prefix}-follow`} name="next_follow_up_date" type="date" required min={todayInput()} defaultValue={record?.next_follow_up_date ?? ""} />
                </div>
              )}
            </div>
          </fieldset>
        )}
        {structured && (["assessment", "recommendations"] as const).map((group) => (
          <fieldset className="form-section" key={group}>
            <legend>{group === "assessment" ? "Assessment" : "Recommendations"}</legend>
            <div className="form-grid">
              {CAREER_LIST_FIELDS.filter((f) => f.group === group).map((f) => (
                <div className="field" key={f.key}>
                  <label htmlFor={`${prefix}-${f.key}`}>{f.label}</label>
                  <input id={`${prefix}-${f.key}`} name={f.key} defaultValue={listText(record?.[f.key])} aria-describedby={`${prefix}-${group}-help`} />
                </div>
              ))}
              {group === "assessment" && (
                <div className="field">
                  <label htmlFor={`${prefix}-global`}>Interested in global education</label>
                  <select id={`${prefix}-global`} name="global_education_interest" defaultValue={yesNo(record?.global_education_interest)}>
                    <option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option>
                  </select>
                </div>
              )}
            </div>
            <p id={`${prefix}-${group}-help`} className="field-help muted">Separate items with commas.</p>
          </fieldset>
        ))}
        {structured && (
          <fieldset className="form-section">
            <legend>Parent participation</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor={`${prefix}-parent`}>Parent participated</label>
                <select id={`${prefix}-parent`} name="parent_participated" defaultValue={yesNo(record?.parent_participated)}>
                  <option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor={`${prefix}-parent-note`}>Participation note (optional)</label>
                <input id={`${prefix}-parent-note`} name="parent_participation_note" maxLength={500} defaultValue={record?.parent_participation_note ?? ""} />
              </div>
            </div>
          </fieldset>
        )}
        <fieldset className="form-section">
          <legend>Counsellor notes</legend>
          <div className="field full">
            <label htmlFor={`${prefix}-notes`}>Notes</label>
            <textarea id={`${prefix}-notes`} name="notes" required={!structured || status === "completed" || status === "follow_up_required"} defaultValue={record?.notes ?? ""} />
          </div>
        </fieldset>
        <div className="actions">
          <button className="btn" id={`${prefix}-save`}>{busy ? "Saving…" : editing ? "Save changes" : "Save record"}</button>
          {editing && <button type="button" className="btn secondary" onClick={onCancel}>Cancel</button>}
        </div>
      </fieldset>
      {message && <FormMessage message={message} />}
      {stale && <button type="button" className="btn secondary small" onClick={() => { router.refresh(); onCancel(); }}>Reload</button>}
    </form>
  );
}
