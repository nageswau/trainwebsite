"use client";

import { useEffect, useId, useMemo, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { batchTopicsUrl, topicCompletionsUrl, type BatchTopics } from "@/lib/itProgress";

type Student = { enrollment_id: string; student: string; student_code: string | null; status: string };

/** itc-022 (DEC-SCOPE-365 P6): tick a programme topic off for many students of a batch at once. The students are the batch's active
 *  enrolments (from the batch progress endpoint the table above reads); the topics are the IT Admin's progress plan. */
export default function TrainerTopicsPanel({ batches, onChanged }: { batches: { id: string; name: string }[]; onChanged?: () => void }) {
  const [batch, setBatch] = useState("");
  const [topics, setTopics] = useState<BatchTopics | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [failed, setFailed] = useState("");
  const [topic, setTopic] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const id = useId();
  const selected = batches.some(item => item.id === batch) ? batch : batches[0]?.id ?? "";

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setFailed("");
    Promise.all([sendRequest(batchTopicsUrl(selected), { method: "GET" }), sendRequest(`/api/v1/workflows/it/batches/${selected}/progress`, { method: "GET" })]).then(([t, p]) => {
      if (cancelled) return;
      if (!t.ok || !p.ok || !Array.isArray(t.data.modules) || !Array.isArray(p.data.students)) {
        setTopics(null);
        return setFailed((!t.ok && t.message) || (!p.ok && p.message) || "Topics could not be loaded.");
      }
      setTopics(t.data as unknown as BatchTopics);
      setStudents((p.data.students as Student[]).filter(s => s.status === "active"));
    });
    return () => {
      cancelled = true;
    };
  }, [selected, reload]);

  const all = useMemo(() => topics?.modules.flatMap(m => m.topics.map(t => ({ ...t, module: m.title }))) ?? [], [topics]);
  const current = all.find(t => t.id === topic) ?? all[0];
  const done = new Set(current?.completed_enrollment_ids ?? []);

  function pickBatch(value: string) {
    setBatch(value);
    setTopics(null);
    setTopic("");
    setPicked(new Set());
    setMessage("");
  }

  function toggle(enrollmentId: string, on: boolean) {
    setPicked(previous => {
      const next = new Set(previous);
      if (on) next.add(enrollmentId);
      else next.delete(enrollmentId);
      return next;
    });
  }

  async function mark(completed: boolean) {
    if (!current || !picked.size || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    const outcome = await sendJson(topicCompletionsUrl(selected, current.id), "PUT", { enrollment_ids: [...picked], completed });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message || "The topic could not be updated.");
    const count = picked.size;
    setPicked(new Set());
    setMessage(`"${current.title}" marked ${completed ? "complete" : "not complete"} for ${count} ${count === 1 ? "student" : "students"}.`);
    setReload(n => n + 1);
    onChanged?.();
  }

  let body;
  if (!batches.length) body = null;
  else if (failed)
    body = (
      <p className="form-error" role="alert" style={{ margin: 0 }}>
        {failed} <button type="button" className="btn small secondary" onClick={() => setReload(n => n + 1)}>Try again</button>
      </p>
    );
  else if (!topics) body = <p className="muted" role="status" style={{ margin: 0 }}>Loading topics…</p>;
  else if (!all.length) body = <p className="muted" style={{ margin: 0 }}>This course has no topics yet. The IT Admin adds them under Progress Plans.</p>;
  else
    body = (
      <>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-topic`}>Topic</label>
          <select id={`${id}-topic`} className="select" value={current?.id ?? ""} onChange={event => { setTopic(event.target.value); setPicked(new Set()); setMessage(""); }}>
            {topics.modules.map(m => (
              <optgroup key={m.id} label={m.title}>
                {m.topics.map(t => <option key={t.id} value={t.id}>{t.title} ({t.completed_enrollment_ids.length} done)</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        {!students.length ? (
          <p className="muted" style={{ margin: 0 }}>No active student in this batch.</p>
        ) : (
          <fieldset style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, margin: 0, display: "grid", gap: 6 }}>
            <legend style={{ padding: "0 4px" }}>Students</legend>
            <label className="check">
              <input type="checkbox" checked={picked.size === students.length} onChange={event => setPicked(event.target.checked ? new Set(students.map(s => s.enrollment_id)) : new Set())} /> Select all ({students.length})
            </label>
            {students.map(s => (
              <label key={s.enrollment_id} className="check">
                <input type="checkbox" checked={picked.has(s.enrollment_id)} onChange={event => toggle(s.enrollment_id, event.target.checked)} />{" "}
                {s.student}{s.student_code ? ` · ${s.student_code}` : ""} {done.has(s.enrollment_id) ? <span className="status">Done</span> : <span className="muted">Not done</span>}
              </label>
            ))}
          </fieldset>
        )}
        {message && <p className="status" role="status" style={{ margin: 0, justifySelf: "start" }}>{message}</p>}
        {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <div className="actions">
          <button type="button" className="btn small" disabled={busy || !picked.size} onClick={() => void mark(true)}>{busy ? "Saving…" : `Mark complete (${picked.size})`}</button>
          <button type="button" className="btn small ghost" disabled={busy || !picked.size} onClick={() => void mark(false)}>Mark not complete</button>
        </div>
        {topics.computed && <p className="muted" style={{ margin: 0, fontSize: 13 }}>This course works progress out from topics, so the table above updates too.</p>}
      </>
    );

  return (
    <section className="action-card" aria-labelledby={`${id}-title`} style={{ display: "grid", gap: 12 }}>
      <h3 id={`${id}-title`}>Topics covered</h3>
      {batches.length > 1 && (
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-batch`}>Batch</label>
          <select id={`${id}-batch`} className="select" value={selected} onChange={event => pickBatch(event.target.value)}>
            {batches.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
      )}
      {body}
    </section>
  );
}
