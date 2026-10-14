"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { roleLabel } from "@/lib/managementDiscussions";
import {
  formatTarget, groupByVertical, PLAN_STATUS_LABEL, PLANS_API, type PlanDetail, type PlanItem, type PlanOptions, type PlanStatus,
} from "@/lib/managementPlans";
import { PRIORITY_LABEL, type TaskPriority } from "@/lib/managementTasks";
import { useHydrated } from "@/lib/useHydrated";

type ItemValues = { vertical: string; text: string; kpi: string; target: string };
type Write = (url: string, method: "POST" | "PATCH" | "DELETE", body?: unknown) => Promise<SendOutcome | null>;
const CLOSED = "This plan is closed. Reopen it to change it.";
const CHECK = "Check the highlighted fields.";

const tidy = (text: string) => text.trim().replace(/\s+/g, " ");

function fromItem(item: PlanItem): ItemValues {
  return { vertical: item.vertical, text: item.text, kpi: item.kpi ?? "", target: item.target === null ? "" : String(Number(item.target)) };
}

/** The item as the API takes it: a free-text item has neither KPI nor target (PN4). */
function itemBody(values: ItemValues): Record<string, string | null> {
  const base = { vertical: values.vertical, text: tidy(values.text) };
  return values.kpi ? { ...base, kpi: values.kpi, target: values.target.trim() } : { ...base, kpi: null, target: null };
}

/** What the browser can check before sending; the API checks everything again (the catalogue, whole-number counts, limits). */
function validate(values: ItemValues): Record<string, string> {
  const errors: Record<string, string> = {};
  const length = tidy(values.text).length;
  if (length < 2 || length > 200) errors.text = "Give the item (2-200 characters)";
  if (values.kpi && !(Number(values.target) > 0)) errors.target = "Give the target for this KPI";
  return errors;
}

// One item's fields, for adding an item and for changing one. `onSave` gets the API body (only the changed fields for an edit).
function ItemForm({ id, label, initial, options, submitLabel, busy, onSave, onCancel }: {
  id: string; label: string; initial: ItemValues; options: PlanOptions; submitLabel: string; busy: boolean;
  onSave: (body: Record<string, string | null>) => Promise<SendOutcome | null>; onCancel?: () => void;
}) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const kpi = options.kpis.find((k) => k.key === values.kpi);
  const set = (key: keyof ItemValues, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => Object.fromEntries(Object.entries(e).filter(([field]) => field !== key)));
  };
  const props = (key: string) => ({ id: `${id}-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${id}-${key}-error` : undefined });
  const error = (key: string) => errors[key] && <p className="form-error" id={`${id}-${key}-error`}>{errors[key]}</p>;

  async function save() {
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage(CHECK);
      document.getElementById(`${id}-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    let body = itemBody(values);
    if (onCancel) {
      const before = itemBody(initial);
      body = Object.fromEntries(Object.entries(body).filter(([key, value]) => value !== before[key]));
      if (Object.keys(body).length === 0) return onCancel();
    } else if (!values.kpi) {
      body = { vertical: body.vertical, text: body.text };
    }
    setMessage("");
    const saved = await onSave(body);
    if (!saved) return;
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? CHECK : saved.message);
      return;
    }
    if (onCancel) onCancel();
    else setValues((v) => ({ ...v, text: "", kpi: "", target: "" })); // the next item usually shares the vertical
  }

  return (
    <form className="form" noValidate aria-label={label} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${id}-vertical`}>Vertical</label>
          <select value={values.vertical} onChange={(e) => set("vertical", e.target.value)} {...props("vertical")}>
            {options.verticals.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
          </select>
          {error("vertical")}
        </div>
        <div className="field">
          <label htmlFor={`${id}-kpi`}>KPI</label>
          <select value={values.kpi} onChange={(e) => set("kpi", e.target.value)} {...props("kpi")}>
            <option value="">None — a free-text item</option>
            {options.kpis.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
          {kpi && <p className="muted" style={{ fontSize: 13, margin: 0 }}>{kpi.definition}</p>}
          {error("kpi")}
        </div>
        {kpi && (
          <div className="field">
            <label htmlFor={`${id}-target`}>Target</label>
            <input type="number" inputMode={kpi.unit === "inr" ? "decimal" : "numeric"} min={kpi.unit === "inr" ? 0.01 : 1} step={kpi.unit === "inr" ? 0.01 : 1}
              value={values.target} onChange={(e) => set("target", e.target.value)} {...props("target")} />
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>{kpi.unit === "inr" ? "In rupees" : "A whole number"}</p>
            {error("target")}
          </div>
        )}
      </div>
      <div className="field">
        <label htmlFor={`${id}-text`}>Item</label>
        <input type="text" maxLength={200} value={values.text} onChange={(e) => set("text", e.target.value)} {...props("text")} />
        {error("text")}
      </div>
      {error("done")}
      {message && <p className="form-error" role="alert">{message}</p>}
      <div className="actions">
        <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
        {onCancel && <button className="btn ghost small" type="button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

// PN10: a mgmt-028 task from an item; the item's text is the title.
function TaskForm({ item, options, today, busy, onSave, onCancel }: {
  item: PlanItem; options: PlanOptions; today: string; busy: boolean; onSave: (body: Record<string, string>) => Promise<SendOutcome | null>; onCancel: () => void;
}) {
  const [values, setValues] = useState<{ owner_user_id: string; priority: TaskPriority; deadline: string }>({ owner_user_id: "", priority: "medium", deadline: today });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const id = `task-${item.id}`;
  const props = (key: string) => ({ id: `${id}-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${id}-${key}-error` : undefined });
  const error = (key: string) => errors[key] && <p className="form-error" id={`${id}-${key}-error`}>{errors[key]}</p>;

  async function save() {
    const found: Record<string, string> = {};
    if (!values.owner_user_id) found.owner_user_id = "Choose the owner";
    if (!values.deadline) found.deadline = "Choose the deadline";
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage(CHECK);
      document.getElementById(`${id}-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    setMessage("");
    const saved = await onSave(values);
    if (saved && !saved.ok) {
      const placed = fieldErrors(saved.detail);
      setErrors(placed);
      setMessage(Object.keys(placed).length ? CHECK : saved.message);
    }
  }

  return (
    <form className="form" noValidate aria-label={`Task for ${item.text}`} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${id}-owner_user_id`}>Owner</label>
          <select value={values.owner_user_id} onChange={(e) => setValues((v) => ({ ...v, owner_user_id: e.target.value }))} {...props("owner_user_id")}>
            <option value="">Choose a staff member</option>
            {options.users.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({roleLabel(p.role)})</option>)}
          </select>
          {error("owner_user_id")}
        </div>
        <div className="field">
          <label htmlFor={`${id}-priority`}>Priority</label>
          <select value={values.priority} onChange={(e) => setValues((v) => ({ ...v, priority: e.target.value as TaskPriority }))} {...props("priority")}>
            {Object.entries(PRIORITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          {error("priority")}
        </div>
        <div className="field">
          <label htmlFor={`${id}-deadline`}>Deadline</label>
          <input type="date" min={today} value={values.deadline} onChange={(e) => setValues((v) => ({ ...v, deadline: e.target.value }))} {...props("deadline")} />
          {error("deadline")}
        </div>
      </div>
      {message && <p className="form-error" role="alert">{message}</p>}
      <div className="actions">
        <button className="btn small" type="submit" disabled={busy}>{busy ? "Creating…" : "Create task"}</button>
        <button className="btn ghost small" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

// mgmt-026 (EVID-017 §25, PN3/PN4/PN9/PN10/PN13/PN14): the plan by vertical -- add, change and remove items, tick free-text items done,
// make a task from an item, and set the plan's status. Items come from the server page; every write refreshes it, so the progress
// table above recounts. One write at a time: a ref blocks a double click, the API's plan lock serialises everyone else.
export default function ManagementPlanEditor({ plan, options, today }: { plan: PlanDetail; options: PlanOptions; today: string }) {
  const router = useRouter();
  const ready = useHydrated();
  const sending = useRef(false);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState<{ id: string; mode: "edit" | "task" } | null>(null);
  const [status, setStatus] = useState<PlanStatus>(plan.status);
  const [notice, setNotice] = useState("");
  const [problem, setProblem] = useState("");
  const closed = plan.status === "closed";
  const base = `${PLANS_API}/${plan.month}`;
  const kpiOf = (key: string | null) => options.kpis.find((k) => k.key === key);

  const write = (key: string): Write => async (url, method, body) => {
    if (sending.current) return null;
    sending.current = true;
    setBusy(key);
    setNotice("");
    setProblem("");
    const result = method === "DELETE" ? await sendRequest(url, { method }) : await sendJson(url, method, body);
    sending.current = false;
    setBusy("");
    if (result.ok) router.refresh();
    return result;
  };

  async function quick(key: string, url: string, method: "PATCH" | "DELETE", body: unknown, done: string) {
    const result = await write(key)(url, method, body);
    if (!result) return;
    if (result.ok) setNotice(done);
    else setProblem(fieldErrors(result.detail).done ?? result.message);
  }

  function remove(item: PlanItem) {
    if (!window.confirm(`Remove "${item.text}" from this plan? Tasks made from it stay.`)) return;
    void quick(`remove-${item.id}`, `${base}/items/${item.id}`, "DELETE", undefined, `Removed "${item.text}".`);
  }

  async function makeTask(item: PlanItem, body: Record<string, string>) {
    const result = await write(`task-${item.id}`)(`${base}/items/${item.id}/tasks`, "POST", body);
    if (result?.ok) {
      const owner = options.users.find((u) => u.id === body.owner_user_id);
      setOpen(null);
      setNotice(`Task created for ${owner?.full_name ?? "the owner"}. It is in the management to-do.`);
    }
    return result;
  }

  return (
    <section className="card" aria-labelledby="plan-items-title">
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 12, alignItems: "end" }}>
        <h3 id="plan-items-title" style={{ margin: 0 }}>Plan by vertical</h3>
        <form className="actions" aria-label="Change plan status" onSubmit={(e) => { e.preventDefault(); if (status !== plan.status) void quick("status", base, "PATCH", { status }, `Plan status: ${PLAN_STATUS_LABEL[status]}.`); }}>
          <label htmlFor="plan-status">Plan status</label>
          <select id="plan-status" value={status} disabled={!ready || !!busy} onChange={(e) => setStatus(e.target.value as PlanStatus)}>
            {Object.entries(PLAN_STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button className="btn secondary small" type="submit" disabled={!ready || !!busy || status === plan.status}>{busy === "status" ? "Saving…" : "Update status"}</button>
        </form>
      </div>
      <p role="status" className="muted" style={{ fontSize: 14, minHeight: "1em" }}>{notice}</p>
      {problem && <p className="form-error" role="alert">{problem}</p>}
      {closed ? (
        <p className="status closed">{CLOSED}</p>
      ) : (
        <div className="action-card" style={{ marginBottom: 18 }}>
          <h4 style={{ marginTop: 0 }}>Add an item</h4>
          <ItemForm id="new-item" label="Add item" initial={{ vertical: options.verticals[0]?.key ?? "", text: "", kpi: "", target: "" }} options={options}
            submitLabel="Add item" busy={!ready || busy === "add"} onSave={(body) => write("add")(`${base}/items`, "POST", body)} />
        </div>
      )}
      {groupByVertical(plan.items, options.verticals).map((group) => (
        <section key={group.key} aria-labelledby={`vertical-${group.key}`} style={{ marginBottom: 18 }}>
          <h4 id={`vertical-${group.key}`}>{group.label} ({group.items.length})</h4>
          {group.items.length === 0 ? (
            <p className="muted" style={{ fontSize: 14 }}>No items in this vertical.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
              {group.items.map((item) => {
                const kpi = kpiOf(item.kpi);
                const editing = open?.id === item.id && open.mode === "edit";
                const tasking = open?.id === item.id && open.mode === "task";
                return (
                  <li key={item.id} className="action-card">
                    {editing ? (
                      <ItemForm id={`item-${item.id}`} label={`Edit ${item.text}`} initial={fromItem(item)} options={options} submitLabel="Save"
                        busy={busy === `edit-${item.id}`} onSave={(body) => write(`edit-${item.id}`)(`${base}/items/${item.id}`, "PATCH", body)} onCancel={() => setOpen(null)} />
                    ) : (
                      <>
                        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                          {kpi ? (
                            <strong style={{ overflowWrap: "anywhere" }}>{item.text}</strong>
                          ) : (
                            <label style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 700, overflowWrap: "anywhere" }}>
                              <input type="checkbox" checked={item.done} aria-label={`Done: ${item.text}`} disabled={!ready || closed || !!busy}
                                onChange={(e) => void quick(`done-${item.id}`, `${base}/items/${item.id}`, "PATCH", { done: e.target.checked }, `"${item.text}" marked ${e.target.checked ? "done" : "not done"}.`)} />
                              <span style={item.done ? { textDecoration: "line-through" } : undefined}>{item.text}</span>
                            </label>
                          )}
                          {!closed && (
                            <div className="actions">
                              <button className="btn secondary small" type="button" disabled={!ready || !!busy} aria-label={`Edit ${item.text}`} onClick={() => setOpen({ id: item.id, mode: "edit" })}>Edit</button>
                              <button className="btn secondary small" type="button" disabled={!ready || !!busy} aria-label={`Create task from ${item.text}`} onClick={() => setOpen({ id: item.id, mode: "task" })}>Create task</button>
                              <button className="btn ghost small" type="button" disabled={!ready || !!busy} aria-label={`Remove ${item.text}`} onClick={() => remove(item)}>Remove</button>
                            </div>
                          )}
                        </div>
                        <div className="muted" style={{ fontSize: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {kpi && item.target !== null ? <span>{kpi.label} · Target {formatTarget(item.target, kpi.unit)}</span> : <span>Free-text item{item.done ? " · Done" : ""}</span>}
                          {item.task_count > 0 && <span>· {item.task_count} {item.task_count === 1 ? "task" : "tasks"}</span>}
                        </div>
                        {tasking && <TaskForm item={item} options={options} today={today} busy={busy === `task-${item.id}`} onSave={(body) => makeTask(item, body)} onCancel={() => setOpen(null)} />}
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ))}
    </section>
  );
}
