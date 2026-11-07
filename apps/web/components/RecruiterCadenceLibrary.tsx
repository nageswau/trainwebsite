"use client";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import {
  approvedTemplates, type Cadence, type CadenceList, CADENCES_URL, cadenceUrl, CHANNELS, DESCRIPTION_MAX, MAX_DAY, MAX_STEPS, NAME_MAX,
  type StepTemplate, stepsError, stepsSummary,
} from "@/lib/recruiterCadences";

type StepRow = { day: string; channel: string; template_id: string };
type Draft = { name: string; description: string; steps: StepRow[] };
const BLANK: Draft = { name: "", description: "", steps: [{ day: "0", channel: "email", template_id: "" }, { day: "3", channel: "linkedin", template_id: "" }] };
const draftOf = (c: Cadence): Draft => ({
  name: c.name, description: c.description ?? "",
  steps: c.steps.map((s) => ({ day: String(s.day), channel: s.channel, template_id: s.template?.id ?? "" })),
});

/** pob-008 (DEC-SCOPE-423 B5): the Team Lead's outreach cadences -- ordered steps (day, channel, optional approved template). Recruiters pick
 *  one on an outreach message; a run keeps its own copy, so an edit here never changes a run in progress. The API checks every rule. */
function CadenceForm({ cadence, templates, onSaved, onCancel }: {
  cadence: Cadence | null; templates: StepTemplate[] | null; onSaved: (text: string) => void; onCancel: () => void;
}) {
  const id = useId();
  const [v, setV] = useState<Draft>(cadence ? draftOf(cadence) : BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const setStep = (i: number, patch: Partial<StepRow>) => setV({ ...v, steps: v.steps.map((s, j) => (j === i ? { ...s, ...patch, ...(patch.channel ? { template_id: "" } : {}) } : s)) });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const missing: Record<string, string> = {};
    if (!v.name.trim()) missing.name = "Enter a name";
    const steps = stepsError(v.steps);
    if (steps) missing.steps = steps;
    if (Object.keys(missing).length) return setErrors(missing);
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const body = {
      name: v.name.trim(), description: v.description.trim() || null,
      steps: v.steps.map((s) => ({ day: Number(s.day), channel: s.channel, template_id: s.template_id || null })),
    };
    const result = await sendJson(cadence ? cadenceUrl(cadence.id) : CADENCES_URL, cadence ? "PATCH" : "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return onSaved(cadence ? "Cadence saved." : "Cadence added.");
    const detail = Array.isArray(result.detail) ? (result.detail as { loc?: unknown[]; msg?: string }[]) : [];
    const placed = Object.fromEntries(detail.filter((d) => Array.isArray(d.loc) && typeof d.loc[1] === "string").map((d) => [d.loc![1] as string, (d.msg ?? "").replace(/^Value error, /, "")]));
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message);
  }

  const fid = (key: string) => `${id}-${key}`;
  return (
    <form aria-label={cadence ? `Edit ${cadence.name}` : "Add a cadence"} noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}
      className="action-card" style={{ display: "grid", gap: 8, marginBottom: 16 }}>
      <h3 style={{ margin: 0 }}>{cadence ? `Edit ${cadence.name}` : "Add a cadence"}</h3>
      <div className="field">
        <label htmlFor={fid("name")}>Name (required)</label>
        <input id={fid("name")} maxLength={NAME_MAX} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} autoFocus
          aria-invalid={errors.name ? true : undefined} aria-describedby={errors.name ? `${fid("name")}-error` : undefined} />
        {errors.name && <p id={`${fid("name")}-error`} className="form-error">{errors.name}</p>}
      </div>
      <div className="field">
        <label htmlFor={fid("description")}>Description (optional)</label>
        <input id={fid("description")} maxLength={DESCRIPTION_MAX} value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }} aria-describedby={`${fid("steps")}-hint${errors.steps ? ` ${fid("steps")}-error` : ""}`}>
        <legend style={{ fontWeight: 600 }}>Steps</legend>
        <p id={`${fid("steps")}-hint`} className="muted" style={{ margin: 0, fontSize: 13 }}>
          Step 1 (day 0) is the outreach that starts the cadence. If the contact has not replied by a later step&rsquo;s day, that step becomes a follow-up.
        </p>
        {v.steps.map((s, i) => {
          const options = (templates ?? []).filter((t) => t.channel === s.channel);
          return (
            <div key={i} role="group" aria-label={`Step ${i + 1}`} style={{ display: "grid", gap: 8, alignItems: "end", gridTemplateColumns: "repeat(auto-fit, minmax(min(9rem, 100%), 1fr))" }}>
              <div className="field">
                <label htmlFor={fid(`day-${i}`)}>Step {i + 1} day</label>
                <input id={fid(`day-${i}`)} type="number" inputMode="numeric" min={0} max={MAX_DAY} step={1} value={s.day} onChange={(e) => setStep(i, { day: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor={fid(`channel-${i}`)}>Step {i + 1} channel</label>
                <select id={fid(`channel-${i}`)} value={s.channel} onChange={(e) => setStep(i, { channel: e.target.value })}>
                  {CHANNELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor={fid(`template-${i}`)}>Step {i + 1} template</label>
                <select id={fid(`template-${i}`)} value={s.template_id} onChange={(e) => setStep(i, { template_id: e.target.value })} disabled={templates === null}>
                  <option value="">No template</option>
                  {options.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  {s.template_id && !options.some((t) => t.id === s.template_id) && <option value={s.template_id}>No longer approved — choose another</option>}
                </select>
              </div>
              <div>
                <button type="button" className="btn secondary small" disabled={v.steps.length <= 2} onClick={() => setV({ ...v, steps: v.steps.filter((_, j) => j !== i) })}>
                  Remove<span className="visually-hidden"> step {i + 1}</span>
                </button>
              </div>
            </div>
          );
        })}
        {errors.steps && <p id={`${fid("steps")}-error`} className="form-error" role="alert">{errors.steps}</p>}
        <div>
          <button type="button" className="btn secondary small" disabled={v.steps.length >= MAX_STEPS}
            onClick={() => setV({ ...v, steps: [...v.steps, { day: String(Math.min(MAX_DAY, Number(v.steps.at(-1)?.day || 0) + 3)), channel: "call", template_id: "" }] })}>
            Add step
          </button>
        </div>
      </fieldset>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : cadence ? "Save cadence" : "Add cadence"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

export default function RecruiterCadenceLibrary() {
  const [list, setList] = useState<CadenceList | null>(null);
  const [failed, setFailed] = useState(false);
  const [templates, setTemplates] = useState<StepTemplate[] | null>(null);
  const [editing, setEditing] = useState<Cadence | "new" | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [version, setVersion] = useState(0);

  const load = useCallback((signal: AbortSignal) => {
    fetch(`${CADENCES_URL}?include_inactive=true`, { signal })
      .then(async (r) => (r.ok ? setList(await r.json()) : setFailed(true)))
      .catch(() => !signal.aborted && setFailed(true));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, version]);
  useEffect(() => {
    if (!list?.can_edit) return;
    const controller = new AbortController();
    approvedTemplates(controller.signal).then(setTemplates).catch(() => !controller.signal.aborted && setTemplates([]));
    return () => controller.abort();
  }, [list?.can_edit]);

  async function toggle(c: Cadence) {
    setNotice(null);
    const result = await sendJson(cadenceUrl(c.id), "PATCH", { active: !c.active });
    setNotice(result.ok ? { ok: true, text: `${c.name} ${c.active ? "deactivated" : "activated"}.` } : { ok: false, text: result.message });
    if (result.ok) setVersion((n) => n + 1);
  }

  if (failed) return <p className="form-error" role="alert">The cadences could not be loaded. Refresh the page to try again.</p>;
  if (!list) return <p className="muted" role="status">Loading cadences…</p>;
  return (
    <div>
      {notice && <p className={notice.ok ? "muted" : "form-error"} role={notice.ok ? "status" : "alert"}>{notice.text}</p>}
      {list.can_edit && editing === null && (
        <div className="actions" style={{ marginBottom: 12 }}>
          <button type="button" className="btn small" onClick={() => setEditing("new")}>Add cadence</button>
        </div>
      )}
      {editing !== null && (
        <CadenceForm key={editing === "new" ? "new" : editing.id} cadence={editing === "new" ? null : editing} templates={templates}
          onCancel={() => setEditing(null)} onSaved={(text) => { setEditing(null); setNotice({ ok: true, text }); setVersion((n) => n + 1); }} />
      )}
      {!list.items.length ? (
        <p className="muted">No cadences yet.{list.can_edit ? " Add one to let recruiters follow up on outreach that gets no reply." : ""}</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {list.items.map((c) => (
            <li key={c.id} className="action-card">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: 0, fontSize: "1rem" }}>{c.name}{!c.active && <span className="muted"> (inactive)</span>}</h3>
                {list.can_edit && (
                  <div className="actions">
                    <button type="button" className="btn secondary small" onClick={() => setEditing(c)}>Edit<span className="visually-hidden"> {c.name}</span></button>
                    <button type="button" className="btn secondary small" onClick={() => void toggle(c)}>
                      {c.active ? "Deactivate" : "Activate"}<span className="visually-hidden"> {c.name}</span>
                    </button>
                  </div>
                )}
              </div>
              {c.description && <p style={{ margin: "4px 0" }}>{c.description}</p>}
              <p className="muted" style={{ margin: 0 }}>{stepsSummary(c.steps)}</p>
              {c.steps.some((s) => s.template) && (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Templates: {c.steps.map((s, i) => (s.template ? `step ${i + 1} ${s.template.name}` : null)).filter(Boolean).join("; ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
