"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, type RefObject, useRef, useState } from "react";

import SchoolSkillAlert, { alertFor, type SkillAlertState } from "@/components/SchoolSkillAlert";
import { MODULE_LABEL, batchDraftErrors, send, type SkillBatch, type SkillModule } from "@/lib/skills";
import type { SchoolRef } from "@/lib/transfers";

// ENH-011 spec §7: create a batch for one school in the counselor's portfolio, then open it. A server 422 marks the field it names;
// the entry is always kept on a failure.
const URL = "/api/v1/school/career-counselor/skill-batches";
const FIELD_ORDER = ["school_id", "title", "topic", "trainer_name", "start_date", "end_date"];
type Draft = { school_id: string; module_type: SkillModule; title: string; topic: string; trainer_name: string; start_date: string; end_date: string };

export default function SchoolSkillBatchForm({ schools, titleRef }: { schools: SchoolRef[]; titleRef: RefObject<HTMLInputElement | null> }) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>({ school_id: schools.length === 1 ? schools[0].id : "", module_type: "soft_skills", title: "", topic: "", trainer_name: "", start_date: "", end_date: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [alert, setAlert] = useState<SkillAlertState | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // state is one render late: two clicks in one task would both see busy=false

  const set = (name: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [name]: e.target.value }));
  // One place builds a field's id, so the input, its error message, its `aria-describedby` and the focus lookup cannot drift apart.
  const fieldId = (name: string) => `skill-batch-${name.replaceAll("_", "-")}`;
  const describe = (name: string) => ({
    id: fieldId(name),
    "aria-invalid": errors[name] ? true : undefined,
    "aria-describedby": errors[name] ? `${fieldId(name)}-error` : undefined,
  });
  const error = (name: string) => errors[name] && <span id={`${fieldId(name)}-error`} className="form-error">{errors[name]}</span>;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (sending.current) return;
    const found: Record<string, string> = { ...(draft.school_id ? {} : { school_id: "Choose a school" }), ...batchDraftErrors(draft) };
    if (Object.keys(found).length > 0) {
      setAlert(null);
      setErrors(found);
      // Focus the first invalid field in on-screen order, so a keyboard or screen-reader user lands on what to fix.
      const first = FIELD_ORDER.find((name) => found[name]);
      if (first) document.getElementById(fieldId(first))?.focus();
      return;
    }
    sending.current = true;
    setBusy(true);
    setAlert(null);
    setErrors({});
    const body = { ...draft, topic: draft.topic.trim() || null, trainer_name: draft.trainer_name.trim() || null, end_date: draft.end_date || null };
    const result = await send<SkillBatch>(URL, "POST", body);
    if (result.ok) return router.push(`/school/career-counselor/skills/${result.data.id}`); // stays busy while the page changes
    sending.current = false;
    setBusy(false);
    setErrors(result.fields);
    setAlert(alertFor(result, true));
  }

  return (
    <div className="card">
      <h2>Create a batch</h2>
      <form className="form" onSubmit={submit} noValidate aria-busy={busy}>
        <div className="form-grid">
          {schools.length > 1 ? (
            <div className="field" style={{ minWidth: 0 }}>
              <label htmlFor="skill-batch-school-id">School</label>
              <select className="select" value={draft.school_id} disabled={busy} onChange={set("school_id")} {...describe("school_id")}>
                <option value="" disabled>Select a school</option>
                {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {error("school_id")}
            </div>
          ) : (
            <p className="muted">School: <strong>{schools[0]?.name}</strong></p>
          )}
          <div className="field">
            <label htmlFor="skill-batch-module-type">Skills module</label>
            <select className="select" value={draft.module_type} disabled={busy} onChange={set("module_type")} {...describe("module_type")}>
              {(Object.keys(MODULE_LABEL) as SkillModule[]).map((m) => <option key={m} value={m}>{MODULE_LABEL[m]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="skill-batch-title">Title</label>
            <input ref={titleRef} className="search" required maxLength={160} value={draft.title} disabled={busy} onChange={set("title")} {...describe("title")} />
            {error("title")}
          </div>
          <div className="field">
            <label htmlFor="skill-batch-topic">Topic (optional)</label>
            <input className="search" maxLength={120} placeholder="e.g. Public speaking, Coding" value={draft.topic} disabled={busy} onChange={set("topic")} {...describe("topic")} />
            {error("topic")}
          </div>
          <div className="field">
            <label htmlFor="skill-batch-trainer-name">Trainer name (optional)</label>
            <input className="search" maxLength={120} value={draft.trainer_name} disabled={busy} onChange={set("trainer_name")} {...describe("trainer_name")} />
            {error("trainer_name")}
          </div>
          <div className="field">
            <label htmlFor="skill-batch-start-date">Start date</label>
            <input type="date" className="search" required value={draft.start_date} disabled={busy} onChange={set("start_date")} {...describe("start_date")} />
            {error("start_date")}
          </div>
          <div className="field">
            <label htmlFor="skill-batch-end-date">End date (optional)</label>
            <input type="date" className="search" min={draft.start_date || undefined} value={draft.end_date} disabled={busy} onChange={set("end_date")} {...describe("end_date")} />
            {error("end_date")}
          </div>
        </div>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Creating…" : "Create batch"}</button>
        <SchoolSkillAlert alert={alert} />
      </form>
    </div>
  );
}
