"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent, type ReactNode } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { DISCUSSIONS_HOME, formatDay, roleLabel, STATUS_LABEL, statusClass, type DiscussionOptions, type DiscussionPerson } from "@/lib/managementDiscussions";
import { MEETINGS_API, progressText, type ChainTask, type MeetingDetail } from "@/lib/managementMeetings";
import { PRIORITY_LABEL, priorityClass, TASKS_HOME, type TaskPriority } from "@/lib/managementTasks";

// mgmt-029 (MM6-MM10; AC): Meeting → Minutes → Decision → Task → Deadline → Completion on the meeting's page. The minutes come first;
// from them, management adds the mgmt-027 decisions and mgmt-028 tasks (under a decision or the meeting itself), each with its
// deadline and status, and the roll-up counts every one that isn't cancelled. Every write refreshes the server-rendered page.
type Props = { meeting: MeetingDetail; options: DiscussionOptions; started: boolean };
type Result = { text: string; failed: boolean } | null;

const who = (p: DiscussionPerson | null) => (p ? `${p.full_name} (${roleLabel(p.role)})` : "No one yet");

function TaskLine({ task }: { task: ChainTask }) {
  return (
    <li style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "6px 0" }}>
      <span style={{ fontWeight: 600, overflowWrap: "anywhere" }}>Task: {task.title}</span>
      <span className="muted" style={{ fontSize: 14 }}>{task.owner.full_name} · Due {formatDay(task.deadline)}</span>
      <span className={priorityClass(task.priority)}>{PRIORITY_LABEL[task.priority]} priority</span>
      <span className={statusClass(task.status)}>{STATUS_LABEL[task.status]}</span>
      <Link className="kpi-link" href={`${TASKS_HOME}/${task.id}/edit`} aria-label={`Open task ${task.title}`}>View</Link>
    </li>
  );
}

/** One small form: posts, shows the API's field errors next to its fields, refreshes the page on success. */
function useSend(url: string, after?: () => void) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Result>(null);
  const sending = useRef(false);
  async function send(method: "POST" | "PATCH", body: unknown, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(url, method, body);
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) {
      const placed = fieldErrors(outcome.detail);
      setErrors(placed);
      setResult({ text: Object.keys(placed).length ? "Check the highlighted fields." : outcome.message, failed: true });
      return;
    }
    setErrors({});
    setResult({ text: done, failed: false });
    after?.();
    router.refresh();
  }
  const message = result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>;
  return { busy, errors, setErrors, message, send };
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <p className="form-error" id={`${id}-error`}>{error}</p>}
    </div>
  );
}

const invalid = (id: string, error?: string) => ({ id, "aria-invalid": error ? true : undefined, "aria-describedby": error ? `${id}-error` : undefined });

function Minutes({ meeting }: { meeting: MeetingDetail }) {
  const [text, setText] = useState(meeting.minutes ?? "");
  const { busy, errors, setErrors, message, send } = useSend(`${MEETINGS_API}/${meeting.id}/minutes`);
  function submit(e: FormEvent) {
    e.preventDefault();
    if (text.trim().length < 2) return setErrors({ minutes: "Write the minutes (2-20,000 characters)" });
    void send("POST", { minutes: text.trim() }, "Minutes saved.");
  }
  return (
    <form className="form" noValidate onSubmit={submit} aria-label="Record the minutes">
      <Field id="meeting-minutes" label="Minutes" error={errors.minutes}>
        <textarea rows={6} maxLength={20000} value={text} disabled={busy} onChange={(e) => setText(e.target.value)} {...invalid("meeting-minutes", errors.minutes)} />
      </Field>
      {message}
      <div className="actions"><button className="btn" type="submit" disabled={busy || text.trim() === (meeting.minutes ?? "")}>{busy ? "Saving…" : "Save minutes"}</button></div>
    </form>
  );
}

function AddDecision({ meeting, people }: { meeting: MeetingDetail; people: DiscussionPerson[] }) {
  const empty = { decision: "", responsible_user_id: "", deadline: "" };
  const [values, setValues] = useState(empty);
  const { busy, errors, setErrors, message, send } = useSend(`${MEETINGS_API}/${meeting.id}/decisions`, () => setValues(empty));
  const set = (key: keyof typeof empty, value: string) => setValues((v) => ({ ...v, [key]: value }));
  function submit(e: FormEvent) {
    e.preventDefault();
    const length = values.decision.trim().length;
    if (length < 2 || length > 500) return setErrors({ decision: "Write the decision (2-500 characters)" });
    void send("POST", { decision: values.decision.trim(), responsible_user_id: values.responsible_user_id || null, deadline: values.deadline || null }, "Decision added.");
  }
  return (
    <form className="form action-card" noValidate onSubmit={submit} aria-label="Add a decision">
      <h4 style={{ margin: 0 }}>Add a decision from the minutes</h4>
      <Field id="chain-decision" label="Decision" error={errors.decision}>
        <input type="text" maxLength={500} value={values.decision} disabled={busy} onChange={(e) => set("decision", e.target.value)} {...invalid("chain-decision", errors.decision)} />
      </Field>
      <div className="form-grid">
        <Field id="chain-responsible_user_id" label="Person responsible (optional)" error={errors.responsible_user_id}>
          <select value={values.responsible_user_id} disabled={busy} onChange={(e) => set("responsible_user_id", e.target.value)} {...invalid("chain-responsible_user_id", errors.responsible_user_id)}>
            <option value="">No one yet</option>
            {people.map((p) => <option key={p.id} value={p.id}>{who(p)}</option>)}
          </select>
        </Field>
        <Field id="chain-decision-deadline" label="Decision deadline (optional)" error={errors.deadline}>
          <input type="date" value={values.deadline} disabled={busy} onChange={(e) => set("deadline", e.target.value)} {...invalid("chain-decision-deadline", errors.deadline)} />
        </Field>
      </div>
      {message}
      <div className="actions"><button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Add decision"}</button></div>
    </form>
  );
}

function AddTask({ meeting, people }: { meeting: MeetingDetail; people: DiscussionPerson[] }) {
  const empty = { title: "", owner_user_id: "", priority: "medium" as TaskPriority, deadline: "", decision_id: "" };
  const [values, setValues] = useState(empty);
  const { busy, errors, setErrors, message, send } = useSend(`${MEETINGS_API}/${meeting.id}/tasks`, () => setValues(empty));
  const set = (key: keyof typeof empty, value: string) => setValues((v) => ({ ...v, [key]: value }));
  function submit(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    const length = values.title.trim().length;
    if (length < 2 || length > 200) found.title = "Write the task (2-200 characters)";
    if (!values.owner_user_id) found.owner_user_id = "Choose the owner";
    if (!values.deadline) found.deadline = "Choose the deadline";
    if (Object.keys(found).length) return setErrors(found);
    void send("POST", { title: values.title.trim(), owner_user_id: values.owner_user_id, priority: values.priority, deadline: values.deadline, decision_id: values.decision_id || null }, "Task added.");
  }
  return (
    <form className="form action-card" noValidate onSubmit={submit} aria-label="Add a task">
      <h4 style={{ margin: 0 }}>Add a task from the minutes</h4>
      <Field id="chain-task-title" label="Task" error={errors.title}>
        <input type="text" maxLength={200} value={values.title} disabled={busy} onChange={(e) => set("title", e.target.value)} {...invalid("chain-task-title", errors.title)} />
      </Field>
      <div className="form-grid">
        <Field id="chain-owner_user_id" label="Owner" error={errors.owner_user_id}>
          <select value={values.owner_user_id} disabled={busy} onChange={(e) => set("owner_user_id", e.target.value)} {...invalid("chain-owner_user_id", errors.owner_user_id)}>
            <option value="">Choose…</option>
            {people.map((p) => <option key={p.id} value={p.id}>{who(p)}</option>)}
          </select>
        </Field>
        <Field id="chain-priority" label="Priority">
          <select id="chain-priority" value={values.priority} disabled={busy} onChange={(e) => set("priority", e.target.value)}>
            {Object.entries(PRIORITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        <Field id="chain-task-deadline" label="Deadline" error={errors.deadline}>
          <input type="date" value={values.deadline} disabled={busy} onChange={(e) => set("deadline", e.target.value)} {...invalid("chain-task-deadline", errors.deadline)} />
        </Field>
        <Field id="chain-decision_id" label="Under decision (optional)" error={errors.decision_id}>
          <select value={values.decision_id} disabled={busy} onChange={(e) => set("decision_id", e.target.value)} {...invalid("chain-decision_id", errors.decision_id)}>
            <option value="">The meeting itself</option>
            {meeting.decisions.map((d) => <option key={d.id} value={d.id}>{d.decision}</option>)}
          </select>
        </Field>
      </div>
      {message}
      <div className="actions"><button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Add task"}</button></div>
    </form>
  );
}

function CancelMeeting({ meeting }: { meeting: MeetingDetail }) {
  const { busy, message, send } = useSend(`${MEETINGS_API}/${meeting.id}`);
  function cancel() {
    if (window.confirm(`Cancel “${meeting.title}”? Participants are notified, and a cancelled meeting can't be changed.`)) void send("PATCH", { status: "cancelled" }, "Meeting cancelled.");
  }
  return (
    <div>
      <button className="btn secondary" type="button" disabled={busy} onClick={cancel}>{busy ? "Cancelling…" : "Cancel meeting"}</button>
      {message}
    </div>
  );
}

export default function ManagementMeetingChain({ meeting, options, started }: Props) {
  const recorded = meeting.minutes !== null;
  const open = meeting.status !== "cancelled";
  return (
    <>
      <section aria-labelledby="meeting-minutes-title" className="action-card">
        <h3 id="meeting-minutes-title">Minutes</h3>
        {!open ? (
          <>
            <p className="muted" role="status">This meeting was cancelled.</p>
            {recorded && <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{meeting.minutes}</p>}
          </>
        ) : started ? (
          <Minutes meeting={meeting} />
        ) : (
          <p className="muted" role="status">Minutes can be recorded once the meeting has started.</p>
        )}
        <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>Management only: participants never see the minutes.</p>
        {open && meeting.status === "scheduled" && <CancelMeeting meeting={meeting} />}
      </section>
      <section aria-labelledby="meeting-chain-title" className="action-card">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
          <h3 id="meeting-chain-title" style={{ margin: 0 }}>Decisions and tasks</h3>
          <strong>{progressText(meeting.progress)}</strong>
        </div>
        {meeting.decisions.length === 0 && meeting.tasks.length === 0 && (
          <p className="empty" role="status">{recorded ? "No decisions or tasks recorded from these minutes yet." : "Record the minutes, then add the decisions and tasks that came out of the meeting."}</p>
        )}
        {meeting.decisions.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
            {meeting.decisions.map((d) => (
              <li key={d.id} aria-label={d.decision} style={{ borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 8, overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <strong>Decision: {d.decision}</strong>
                  <span className={statusClass(d.status)}>{STATUS_LABEL[d.status]}</span>
                  <Link className="kpi-link" href={`${DISCUSSIONS_HOME}/${d.id}`} aria-label={`Open decision ${d.decision}`}>View</Link>
                </div>
                <div className="muted" style={{ fontSize: 14 }}>{who(d.responsible)} · {d.deadline ? `Due ${formatDay(d.deadline)}` : "No deadline"}</div>
                {d.tasks.length > 0 && <ul style={{ listStyle: "none", margin: "4px 0 0", paddingLeft: 16 }}>{d.tasks.map((t) => <TaskLine key={t.id} task={t} />)}</ul>}
              </li>
            ))}
          </ul>
        )}
        {meeting.tasks.length > 0 && (
          <>
            <h4 style={{ margin: "12px 0 0" }}>Meeting tasks</h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>{meeting.tasks.map((t) => <TaskLine key={t.id} task={t} />)}</ul>
          </>
        )}
      </section>
      {open && recorded && (
        <div style={{ display: "grid", gap: 14 }}>
          <AddDecision meeting={meeting} people={options.users} />
          <AddTask meeting={meeting} people={options.users} />
        </div>
      )}
    </>
  );
}
