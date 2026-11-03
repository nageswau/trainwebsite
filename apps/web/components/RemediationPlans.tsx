"use client";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { CLOSED, STATUS_LABEL, enrollmentPlansUrl, planUrl, studentPlansUrl, type PlanStatus, type RemediationPlan, type StudentPlans } from "@/lib/itProgress";

const today = () => new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10); // IST, the server's "past" rule
const NEXT: PlanStatus[] = ["open", "in_progress", "completed", "cancelled"];

/** itc-022 (DEC-SCOPE-365 P9): one student's remediation plans. Readers (the batch trainer, the IT counselor, the IT Admin) see every plan;
 *  the batch trainer and the IT Admin add plans and edit them; a plan's owner may move its status. Closed plans are final. */
export default function RemediationPlans({ studentId, viewerId, enrollmentId }: { studentId: string; viewerId?: string; enrollmentId?: string }) {
  const [data, setData] = useState<StudentPlans | null>(null);
  const [failed, setFailed] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const id = useId();

  const load = useCallback(async (signal: { cancelled: boolean }) => {
    setFailed("");
    const outcome = await sendRequest(studentPlansUrl(studentId), { method: "GET" });
    if (signal.cancelled) return;
    if (!outcome.ok || !Array.isArray(outcome.data.items)) return setFailed(outcome.ok ? "Remediation plans could not be loaded." : outcome.message);
    setData(outcome.data as unknown as StudentPlans);
  }, [studentId]);

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load, reload]);

  const writable = data?.enrollments ?? [];
  const target = writable.find(e => e.enrollment_id === enrollmentId) ?? writable[0];

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!target || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy("new");
    setError("");
    const outcome = await sendJson(enrollmentPlansUrl(String(form.get("enrollment") || target.enrollment_id)), "POST", {
      actions: form.get("actions"),
      due_date: form.get("due_date"),
      owner_user_id: form.get("owner") || null,
    });
    setBusy("");
    if (!outcome.ok) return setError(outcome.message || "The plan could not be saved.");
    setAdding(false);
    setMessage("Remediation plan added.");
    setReload(n => n + 1);
  }

  async function move(plan: RemediationPlan, status: PlanStatus) {
    setBusy(plan.id);
    setError("");
    const outcome = await sendJson(planUrl(plan.id), "PATCH", { status });
    setBusy("");
    if (!outcome.ok) return setError(outcome.message || "The plan could not be updated.");
    setMessage(`Plan marked ${STATUS_LABEL[status].toLowerCase()}.`);
    setReload(n => n + 1);
  }

  const canMove = (plan: RemediationPlan) => !CLOSED.includes(plan.status) && (writable.length > 0 || (!!viewerId && plan.owner_user_id === viewerId));
  return (
    <section aria-labelledby={`${id}-title`} style={{ display: "grid", gap: 8 }}>
      <h4 id={`${id}-title`} style={{ margin: 0 }}>Remediation plans</h4>
      {message && <p className="status" role="status" style={{ margin: 0, justifySelf: "start" }}>{message}</p>}
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          {failed} <button type="button" className="btn small secondary" onClick={() => setReload(n => n + 1)}>Try again</button>
        </p>
      ) : data === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading remediation plans…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No remediation plan yet.</p>
      ) : (
        <ul style={{ display: "grid", gap: 8, margin: 0, paddingLeft: 18 }}>
          {data.items.map(plan => (
            <li key={plan.id}>
              <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{plan.actions}</span>
              <span className="muted" style={{ display: "block", fontSize: 13 }}>
                Due {plan.due_date} · {plan.owner_name ?? "No owner"} · {plan.batch}{plan.risk_flag_id ? " · from an at-risk flag" : ""}
              </span>
              <span className={`status${CLOSED.includes(plan.status) ? "" : " pending"}`}>{STATUS_LABEL[plan.status]}</span>{" "}
              {canMove(plan) && (
                <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
                  {NEXT.filter(s => s !== plan.status).map(s => (
                    <button key={s} type="button" className="btn small ghost" disabled={busy === plan.id} onClick={() => void move(plan, s)} aria-label={`Mark plan "${plan.actions.slice(0, 40)}" ${STATUS_LABEL[s].toLowerCase()}`}>
                      {STATUS_LABEL[s]}
                    </button>
                  ))}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {target && !adding && <div><button type="button" className="btn small secondary" onClick={() => { setAdding(true); setMessage(""); }}>Add remediation plan</button></div>}
      {target && adding && data && (
        <form onSubmit={create} style={{ display: "grid", gap: 8 }} aria-label="New remediation plan">
          {writable.length > 1 && (
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor={`${id}-enrollment`}>Batch</label>
              <select id={`${id}-enrollment`} name="enrollment" className="select" defaultValue={target.enrollment_id}>
                {writable.map(e => <option key={e.enrollment_id} value={e.enrollment_id}>{e.batch}</option>)}
              </select>
            </div>
          )}
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-actions`}>Actions</label>
            <textarea id={`${id}-actions`} name="actions" required maxLength={2000} rows={3} placeholder="e.g. Two extra lab sessions and a weekly check-in" />
          </div>
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))" }}>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor={`${id}-due`}>Due date</label>
              <input id={`${id}-due`} name="due_date" type="date" required min={today()} />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor={`${id}-owner`}>Owner</label>
              <select id={`${id}-owner`} name="owner" className="select" defaultValue={viewerId ?? ""}>
                {!data.owner_options.some(o => o.id === viewerId) && <option value="">Me</option>}
                {data.owner_options.map(o => <option key={o.id} value={o.id}>{o.id === viewerId ? `${o.name} (me)` : `${o.name} (${o.role.replace("_", " ")})`}</option>)}
              </select>
            </div>
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy === "new"}>{busy === "new" ? "Saving…" : "Save remediation plan"}</button>
            <button type="button" className="btn small ghost" onClick={() => { setAdding(false); setError(""); }} disabled={busy === "new"}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
