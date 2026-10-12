"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { roleLabel, STATUS_LABEL, type DiscussionOptions, type DiscussionStatus } from "@/lib/managementDiscussions";
import { PRIORITY_LABEL, TASKS_API, tasksHref, type ManagementTask, type TaskPriority } from "@/lib/managementTasks";
import { useHydrated } from "@/lib/useHydrated";

type Values = { title: string; owner_user_id: string; priority: TaskPriority; deadline: string; status: DiscussionStatus };
type Field = keyof Values;
const AFTER_SAVE = tasksHref({ view: "everyone" }); // a task assigned to someone else is not in "My tasks"

function initial(task: ManagementTask | undefined, today: string): Values {
  if (!task) return { title: "", owner_user_id: "", priority: "medium", deadline: today, status: "open" };
  return { title: task.title, owner_user_id: task.owner.id, priority: task.priority, deadline: task.deadline, status: task.status };
}

function body(values: Values): Record<string, string> {
  return { ...values, title: values.title.trim().replace(/\s+/g, " ") };
}

/** What the browser can check before sending; the API checks everything again (active staff, the deadline window). */
function validate(values: Values, task: ManagementTask | undefined, today: string): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  const title = values.title.trim().length;
  if (title < 2 || title > 200) errors.title = "Give the title (2-200 characters)";
  if (!values.owner_user_id) errors.owner_user_id = "Choose the owner";
  if (!values.deadline) errors.deadline = "Choose the deadline";
  else if (values.deadline !== task?.deadline && values.deadline < today) errors.deadline = "The deadline can't be in the past";
  return errors;
}

// mgmt-028 (MT1/MT6-MT8): a new task or a change to one. An edit sends only the fields that changed, so nothing unchanged is
// re-recorded or re-notified. An owner who has since left still shows (marked inactive), so the current value is never dropped.
export default function ManagementTaskForm({ options, today, task }: { options: DiscussionOptions; today: string; task?: ManagementTask }) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Values>(() => initial(task, today));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one save per double click
  const set = (key: Field, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => Object.fromEntries(Object.entries(e).filter(([field]) => field !== key)));
  };
  const inactiveOwner = task && !options.users.some((u) => u.id === task.owner.id) ? task.owner : null;

  const fieldProps = (key: Field) => ({ id: `task-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `task-${key}-error` : undefined });
  const error = (key: Field) => errors[key] && <p className="form-error" id={`task-${key}-error`}>{errors[key]}</p>;

  async function save() {
    if (sending.current) return;
    const found = validate(values, task, today);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage("Check the highlighted fields.");
      document.getElementById(`task-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    let payload = body(values);
    if (task) {
      const before = body(initial(task, today));
      payload = Object.fromEntries(Object.entries(payload).filter(([key, value]) => value !== before[key]));
      if (Object.keys(payload).length === 0) {
        router.push(AFTER_SAVE);
        return;
      }
    }
    sending.current = true;
    setBusy(true);
    setMessage("");
    const saved = task ? await sendJson(`${TASKS_API}/${task.id}`, "PATCH", payload) : await sendJson(TASKS_API, "POST", payload);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? "Check the highlighted fields." : saved.message);
      sending.current = false;
      setBusy(false);
      return;
    }
    router.push(AFTER_SAVE);
    router.refresh(); // the list may be cached from before this change
  }

  return (
    <form className="form action-card" noValidate aria-label={task ? "Edit task" : "New task"} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="field">
          <label htmlFor="task-title">Title</label>
          <input type="text" maxLength={200} value={values.title} onChange={(e) => set("title", e.target.value)} {...fieldProps("title")} />
          {error("title")}
        </div>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="task-owner_user_id">Owner</label>
            <select value={values.owner_user_id} onChange={(e) => set("owner_user_id", e.target.value)} {...fieldProps("owner_user_id")}>
              <option value="">Choose a staff member</option>
              {inactiveOwner && <option value={inactiveOwner.id}>{inactiveOwner.full_name} ({roleLabel(inactiveOwner.role)}) — inactive</option>}
              {options.users.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({roleLabel(p.role)})</option>)}
            </select>
            {error("owner_user_id")}
          </div>
          <div className="field">
            <label htmlFor="task-priority">Priority</label>
            <select value={values.priority} onChange={(e) => set("priority", e.target.value)} {...fieldProps("priority")}>
              {Object.entries(PRIORITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {error("priority")}
          </div>
          <div className="field">
            <label htmlFor="task-deadline">Deadline</label>
            <input type="date" min={task ? undefined : today} value={values.deadline} onChange={(e) => set("deadline", e.target.value)} {...fieldProps("deadline")} />
            {error("deadline")}
          </div>
          <div className="field">
            <label htmlFor="task-status">Status</label>
            <select value={values.status} onChange={(e) => set("status", e.target.value)} {...fieldProps("status")}>
              {Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {error("status")}
          </div>
        </div>
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>The owner is notified and sees the task in their Management tasks, where they update its status.</p>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : task ? "Save changes" : "Save task"}</button>
          <a className="btn ghost" href={AFTER_SAVE}>Cancel</a>
        </div>
      </fieldset>
    </form>
  );
}
