"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type Context = {
  batches: { id: string; name: string }[];
  students: { id: string; name: string; batch_id: string }[];
};

function errorMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(x => x?.msg || "Invalid input").join("; ");
  return "The operation could not be completed.";
}

export default function TrainerWorkflowForm({ section }: { section: string }) {
  const router = useRouter();
  const [context, setContext] = useState<Context>({ batches: [], students: [] });
  const [batchId, setBatchId] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const students = useMemo(() => context.students.filter(s => String(s.batch_id) === batchId), [context.students, batchId]);

  useEffect(() => {
    fetch("/api/v1/workflows/it/trainer/context")
      .then(async r => {
        const data = await r.json();
        if (!r.ok) throw new Error(errorMessage(data.detail));
        return data as Context;
      })
      .then(data => { setContext(data); if (data.batches[0]) setBatchId(String(data.batches[0].id)); })
      .catch(e => setMessage(e instanceof Error ? e.message : "Unable to load trainer data"));
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formElement = e.currentTarget;
    setBusy(true); setMessage("");
    const form = new FormData(formElement);
    let endpoint = "";
    let payload: Record<string, unknown> = { batch_id: batchId };
    if (section === "attendance") {
      endpoint = "/api/v1/workflows/it/trainer/attendance";
      payload = {
        ...payload,
        session_date: form.get("session_date"),
        records: students.map(student => ({
          student_id: student.id,
          status: form.get(`status_${student.id}`),
          notes: form.get(`notes_${student.id}`),
        })),
      };
    } else if (section === "assignments") {
      endpoint = "/api/v1/workflows/it/trainer/assignments";
      payload = { ...payload, title: form.get("title"), description: form.get("description"), due_date: form.get("due_date"), max_score: Number(form.get("max_score")) };
    } else {
      endpoint = "/api/v1/workflows/it/trainer/assessments";
      payload = { ...payload, title: form.get("title"), description: form.get("description"), scheduled_at: form.get("scheduled_at"), duration_minutes: Number(form.get("duration_minutes")), max_score: Number(form.get("max_score")) };
    }
    const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setMessage(errorMessage(data.detail)); return; }
    setMessage(section === "attendance" ? "Attendance saved." : section === "assignments" ? "Assignment created." : "Assessment created.");
    formElement.reset();
    router.refresh();
  }

  const today = new Date().toISOString().slice(0, 10);
  return <div className="workspace" style={{marginTop:24}}><div className="workspace-head"><strong>{section === "attendance" ? "Mark attendance" : section === "assignments" ? "Create assignment" : "Create assessment"}</strong><span className="badge">Trainer action</span></div><form className="form" style={{padding:24}} onSubmit={submit}>
    <div className="field"><label>Batch</label><select required value={batchId} onChange={e => setBatchId(e.target.value)}><option value="">Select batch</option>{context.batches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
    {section === "attendance" ? <>
      <div className="field"><label>Session date</label><input name="session_date" type="date" defaultValue={today} required/></div>
      {students.length ? <div className="table-wrap"><table className="table"><thead><tr><th>Student</th><th>Status</th><th>Notes</th></tr></thead><tbody>{students.map(student => <tr key={student.id}><td><strong>{student.name}</strong></td><td><select name={`status_${student.id}`} defaultValue="present"><option value="present">Present</option><option value="absent">Absent</option><option value="late">Late</option><option value="excused">Excused</option></select></td><td><input name={`notes_${student.id}`} placeholder="Optional note"/></td></tr>)}</tbody></table></div> : <div className="empty"><p>No active students are enrolled in this batch.</p></div>}
    </> : <>
      <div className="field"><label>Title</label><input name="title" required/></div>
      <div className="field"><label>Description</label><textarea name="description"/></div>
      <div className="field"><label>{section === "assignments" ? "Due date and time" : "Scheduled date and time"}</label><input name={section === "assignments" ? "due_date" : "scheduled_at"} type="datetime-local" required/></div>
      {section === "assessments" && <div className="field"><label>Duration (minutes)</label><input name="duration_minutes" type="number" min="1" defaultValue="60" required/></div>}
      <div className="field"><label>Maximum score</label><input name="max_score" type="number" min="1" defaultValue="100" required/></div>
    </>}
    {message && <div className={message.endsWith(".") ? "form-message" : "form-error"}>{message}</div>}
    <button className="btn" disabled={busy || !batchId || (section === "attendance" && !students.length)}>{busy ? "Saving…" : section === "attendance" ? `Save attendance (${students.length})` : "Save"}</button>
  </form></div>;
}
