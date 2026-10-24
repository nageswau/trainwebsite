"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import {
  COUNSELOR_TASKS_API, LINK_GROUPS, linkValue, parseLink, type CounselorTask, type CounselorTaskOptions,
} from "@/lib/counselorTasks";
import { PRIORITY_LABEL, type TaskPriority } from "@/lib/managementTasks";
import { useHydrated } from "@/lib/useHydrated";

type Values = { title: string; due_on: string; priority: TaskPriority; counselor_user_id: string; link: string };
type Field = keyof Values;
const NO_LINKS: CounselorTaskOptions["links"] = { leads: [], students: [], applications: [] };

function initial(task: CounselorTask | undefined, today: string): Values {
  if (!task) return { title: "", due_on: today, priority: "medium", counselor_user_id: "", link: "" };
  return { title: task.title, due_on: task.due_on, priority: task.priority, counselor_user_id: task.counselor.id, link: linkValue(task.link) };
}

function body(values: Values, admin: boolean): Record<string, unknown> {
  const out: Record<string, unknown> = { title: values.title.trim().replace(/\s+/g, " "), due_on: values.due_on, priority: values.priority, link: parseLink(values.link) };
  if (admin) out.counselor_user_id = values.counselor_user_id;
  return out;
}

/** What the browser can check before sending; the API checks everything again (the counselor, the due window, the link's scope). */
function validate(values: Values, task: CounselorTask | undefined, today: string, admin: boolean): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  const title = values.title.trim().length;
  if (title < 2 || title > 200) errors.title = "Give the title (2-200 characters)";
  if (!values.due_on) errors.due_on = "Choose the due date";
  else if (values.due_on !== task?.due_on && values.due_on < today) errors.due_on = "The due date can't be in the past";
  if (admin && !values.counselor_user_id) errors.counselor_user_id = "Choose the counselor";
  return errors;
}

// ccrm-029 (T1/T3/T4): a new task or a change to one. The counselor adds tasks for themself; the Overseas Admin picks the counselor, and
// the link choices follow that counselor (they are refetched when the counselor changes). An edit sends only the fields that changed.
export default function CounselorTaskForm({ options, today, admin = false, task, onClose }: {
  options: CounselorTaskOptions; today: string; admin?: boolean; task?: CounselorTask; onClose?: () => void;
}) {
  const router = useRouter();
  const ready = useHydrated();
  const [values, setValues] = useState<Values>(() => initial(task, today));
  const [links, setLinks] = useState(options.links);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one save per double click
  const prefix = task ? `task-${task.id}` : "new-task";
  const set = (key: Field, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => Object.fromEntries(Object.entries(e).filter(([field]) => field !== key)));
    setMessage((m) => (m && !m.failed ? null : m)); // QA-02: "Task added." belongs to the last save, not the next entry
  };
  // The current link stays offered even if it has left the counselor's lists (a closed lead, a withdrawn application).
  const currentLink = task?.link && !links[LINK_GROUPS.find((g) => g.type === task.link?.type)!.key].some((o) => o.id === task.link?.id) ? task.link : null;

  async function loadLinks(id: string) {
    if (!id) return setLinks(NO_LINKS);
    const response = await fetch(`${COUNSELOR_TASKS_API}/options?counselor_id=${encodeURIComponent(id)}`, { credentials: "include" }).catch(() => null);
    if (response?.ok) setLinks(((await response.json()) as CounselorTaskOptions).links);
    else setMessage({ text: "This counselor's leads, students and applications can't be loaded right now.", failed: true });
  }

  function chooseCounselor(id: string) {
    set("counselor_user_id", id);
    set("link", "");
    void loadLinks(id);
  }

  // The admin's page loads no links up front; an edit starts from the task's counselor's.
  useEffect(() => {
    if (admin && task) void loadLinks(task.counselor.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, for the task the form opened with
  }, []);

  const fieldProps = (key: Field) => ({ id: `${prefix}-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${prefix}-${key}-error` : undefined });
  const error = (key: Field) => errors[key] && <p className="form-error" id={`${prefix}-${key}-error`}>{errors[key]}</p>;

  async function save() {
    if (sending.current) return;
    const found = validate(values, task, today, admin);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage({ text: "Check the highlighted fields.", failed: true });
      document.getElementById(`${prefix}-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    let payload = body(values, admin);
    if (task) {
      const before = body(initial(task, today), admin);
      payload = Object.fromEntries(Object.entries(payload).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(before[key])));
      if (Object.keys(payload).length === 0) return onClose?.();
    }
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const saved = task ? await sendJson(`${COUNSELOR_TASKS_API}/${task.id}`, "PATCH", payload) : await sendJson(COUNSELOR_TASKS_API, "POST", payload);
    sending.current = false;
    setBusy(false);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage({ text: Object.keys(placed).length ? "Check the highlighted fields." : saved.message, failed: true });
      return;
    }
    router.refresh();
    if (task) return onClose?.();
    setValues(initial(undefined, today));
    setLinks(admin ? NO_LINKS : options.links);
    setMessage({ text: "Task added.", failed: false });
  }

  return (
    <form className="form action-card" noValidate aria-label={task ? `Edit task “${task.title}”` : "New task"} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        {!task && <h3 style={{ margin: 0 }}>Add a task</h3>}
        <div className="field">
          <label htmlFor={`${prefix}-title`}>Title</label>
          <input type="text" maxLength={200} value={values.title} onChange={(e) => set("title", e.target.value)} {...fieldProps("title")} />
          {error("title")}
        </div>
        <div className="form-grid">
          {admin && (
            <div className="field">
              <label htmlFor={`${prefix}-counselor_user_id`}>Counselor</label>
              <select value={values.counselor_user_id} onChange={(e) => void chooseCounselor(e.target.value)} {...fieldProps("counselor_user_id")}>
                <option value="">Choose a counselor</option>
                {task && !options.counselors.some((c) => c.id === task.counselor.id) && <option value={task.counselor.id}>{task.counselor.full_name} — inactive</option>}
                {options.counselors.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
              </select>
              {error("counselor_user_id")}
            </div>
          )}
          <div className="field">
            <label htmlFor={`${prefix}-due_on`}>Due date</label>
            <input type="date" min={task ? undefined : today} value={values.due_on} onChange={(e) => set("due_on", e.target.value)} {...fieldProps("due_on")} />
            {error("due_on")}
          </div>
          <div className="field">
            <label htmlFor={`${prefix}-priority`}>Priority</label>
            <select value={values.priority} onChange={(e) => set("priority", e.target.value)} {...fieldProps("priority")}>
              {Object.entries(PRIORITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${prefix}-link`}>About (optional)</label>
            <select value={values.link} onChange={(e) => set("link", e.target.value)} {...fieldProps("link")}>
              <option value="">{admin && !values.counselor_user_id ? "Choose the counselor first" : "Nothing in particular"}</option>
              {currentLink && <option value={linkValue(currentLink)}>{currentLink.label}</option>}
              {LINK_GROUPS.filter((g) => links[g.key].length > 0).map((g) => (
                <optgroup key={g.type} label={g.label}>
                  {links[g.key].map((o) => <option key={o.id} value={`${g.type}:${o.id}`}>{o.label}</option>)}
                </optgroup>
              ))}
            </select>
            {error("link")}
          </div>
        </div>
        {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : task ? "Save changes" : "Add task"}</button>
          {task && <button className="btn ghost" type="button" onClick={onClose}>Cancel</button>}
        </div>
      </fieldset>
    </form>
  );
}
