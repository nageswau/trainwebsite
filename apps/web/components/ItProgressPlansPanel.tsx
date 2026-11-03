"use client";

import { useEffect, useId, useState, type FormEvent } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { PROGRESS_PLANS_URL, fromCopySource, progressPlanUrl, weightTotal, weightsSummary, type Plan, type PlanModule, type PlanSummary, type Weights } from "@/lib/itProgress";

type Draft = { modules: PlanModule[]; computed: boolean; weights: Record<keyof Weights, string> };
const WEIGHTS: { key: keyof Weights; label: string }[] = [
  { key: "topics", label: "Topics completed" },
  { key: "assignments", label: "Assignments and labs graded" },
  { key: "assessments", label: "Assessments passed" },
];
const toDraft = (plan: Plan): Draft => ({
  modules: plan.modules.map(m => ({ ...m, topics: m.topics.map(t => ({ ...t })) })),
  computed: plan.weights !== null,
  weights: {
    topics: String(plan.weights?.topics ?? 50),
    assignments: String(plan.weights?.assignments ?? 30),
    assessments: String(plan.weights?.assessments ?? 20),
  },
});
const numbers = (w: Draft["weights"]): Weights => ({ topics: Number(w.topics) || 0, assignments: Number(w.assignments) || 0, assessments: Number(w.assessments) || 0 });

/** itc-022 (DEC-SCOPE-365 P1-P3): the IT Admin's progress plan per programme -- modules and topics, and the optional weights that make the
 *  overall progress % computed. Without weights (or without topics) the trainer keeps typing the % in, as before. */
export default function ItProgressPlansPanel() {
  const [rows, setRows] = useState<PlanSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [opening, setOpening] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const id = useId();

  useEffect(() => {
    let cancelled = false;
    fetch(PROGRESS_PLANS_URL)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: PlanSummary[]) => !cancelled && setRows(data))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  async function open(row: PlanSummary) {
    setOpening(row.program_id);
    setError("");
    setMessage("");
    const outcome = await sendRequest(progressPlanUrl(row.program_id), { method: "GET" });
    setOpening("");
    if (!outcome.ok) return setError(outcome.message || "The plan could not be loaded.");
    const loaded = outcome.data as unknown as Plan;
    setPlan(loaded);
    setDraft(toDraft(loaded));
  }

  function close() {
    setPlan(null);
    setDraft(null);
    setError("");
  }

  const change = (modules: PlanModule[]) => draft && setDraft({ ...draft, modules });
  const setModule = (index: number, module: PlanModule) => draft && change(draft.modules.map((m, i) => (i === index ? module : m)));

  function copyFromSyllabus() {
    if (!plan || !draft) return;
    if (draft.modules.length && !window.confirm("Replace the modules below with the syllabus? Saving then removes the current topics and their completion ticks.")) return;
    change(fromCopySource(plan.copy_source));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!plan || !draft || saving) return;
    const weights = draft.computed ? numbers(draft.weights) : null;
    if (weights && weightTotal(weights) !== 100) return setError(`The weights must add up to 100 (they add up to ${weightTotal(weights)}).`);
    setSaving(true);
    setError("");
    const outcome = await sendJson(progressPlanUrl(plan.program_id), "PUT", { modules: draft.modules, weights });
    setSaving(false);
    if (!outcome.ok) return setError(outcome.message || "The plan could not be saved.");
    const saved = outcome.data as unknown as Plan;
    const topics = saved.modules.reduce((sum, m) => sum + m.topics.length, 0);
    setRows(current => current?.map(r => (r.program_id === saved.program_id ? { ...r, modules: saved.modules.length, topics, weights: saved.weights, computed: saved.computed } : r)) ?? null);
    close();
    setMessage(saved.computed ? `Plan for ${saved.program} saved. Progress is now worked out from the formula.` : `Plan for ${saved.program} saved. Trainers keep setting progress by hand.`);
  }

  const total = draft ? weightTotal(numbers(draft.weights)) : 0;
  return (
    <section className="card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16, display: "grid", gap: 12 }}>
      <div>
        <h3 id={`${id}-title`} style={{ fontSize: 18, marginBottom: 6 }}>Progress plans</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          Break a programme into modules and topics that trainers tick off per student. Add weights to work out each student&apos;s overall
          progress from topics, assignments (labs included) and assessments; without weights trainers set the progress by hand.
        </p>
      </div>
      {message && <p className="status" role="status" style={{ margin: 0, justifySelf: "start" }}>{message}</p>}
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the progress plans. Refresh the page to try again.</p>
      ) : rows === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading progress plans…</p>
      ) : rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No programmes yet. Add a programme first.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th scope="col">Programme</th><th scope="col">Plan</th><th scope="col">Overall progress</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.program_id}>
                  <td>{row.program}{!row.active && <div className="muted" style={{ fontSize: 13 }}>Inactive programme</div>}</td>
                  <td className={row.modules ? undefined : "muted"}>{row.modules ? `${row.modules} ${row.modules === 1 ? "module" : "modules"}, ${row.topics} ${row.topics === 1 ? "topic" : "topics"}` : "No modules yet"}</td>
                  <td className={row.computed ? undefined : "muted"}>{row.computed ? weightsSummary(row.weights) : "Set by the trainer"}</td>
                  <td>
                    <button type="button" className="btn small secondary" onClick={() => void open(row)} disabled={opening === row.program_id} aria-label={`Edit progress plan for ${row.program}`}>
                      {opening === row.program_id ? "Opening…" : "Edit plan"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!draft && error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {plan && draft && (
        <form onSubmit={save} aria-labelledby={`${id}-form`} style={{ display: "grid", gap: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
            <h4 id={`${id}-form`} style={{ margin: 0 }}>Progress plan for {plan.program}</h4>
            {plan.copy_source.length > 0 && <button type="button" className="btn small ghost" onClick={copyFromSyllabus}>Copy from syllabus</button>}
          </div>
          {draft.modules.length === 0 && <p className="muted" style={{ margin: 0 }}>No modules yet. Add one, or copy them from the syllabus.</p>}
          <ol style={{ display: "grid", gap: 12, margin: 0, paddingLeft: 20 }}>
            {draft.modules.map((module, mi) => (
              <li key={module.id ?? `new-${mi}`} style={{ display: "grid", gap: 8 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap" }}>
                  <div className="field" style={{ margin: 0, flex: "1 1 16rem" }}>
                    <label htmlFor={`${id}-m${mi}`}>Module {mi + 1}</label>
                    <input id={`${id}-m${mi}`} required maxLength={200} value={module.title} onChange={e => setModule(mi, { ...module, title: e.target.value })} />
                  </div>
                  <button type="button" className="btn small ghost" onClick={() => change(draft.modules.filter((_, i) => i !== mi))} aria-label={`Remove module ${mi + 1}`}>Remove module</button>
                </div>
                <ul style={{ display: "grid", gap: 6, margin: 0, paddingLeft: 16, listStyle: "none" }}>
                  {module.topics.map((topic, ti) => (
                    <li key={topic.id ?? `new-${ti}`} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <label className="sr-only" htmlFor={`${id}-m${mi}-t${ti}`}>Module {mi + 1} topic {ti + 1}</label>
                      <input id={`${id}-m${mi}-t${ti}`} required maxLength={200} placeholder="Topic" value={topic.title} style={{ flex: "1 1 14rem" }}
                        onChange={e => setModule(mi, { ...module, topics: module.topics.map((t, i) => (i === ti ? { ...t, title: e.target.value } : t)) })} />
                      <button type="button" className="btn small ghost" onClick={() => setModule(mi, { ...module, topics: module.topics.filter((_, i) => i !== ti) })} aria-label={`Remove module ${mi + 1} topic ${ti + 1}`}>Remove</button>
                    </li>
                  ))}
                  <li><button type="button" className="btn small secondary" onClick={() => setModule(mi, { ...module, topics: [...module.topics, { title: "" }] })}>Add topic</button></li>
                </ul>
              </li>
            ))}
          </ol>
          <div><button type="button" className="btn small secondary" onClick={() => change([...draft.modules, { title: "", topics: [] }])}>Add module</button></div>

          <fieldset style={{ display: "grid", gap: 8, border: "1px solid var(--line)", borderRadius: 8, padding: 12, margin: 0 }}>
            <legend style={{ padding: "0 4px" }}>Overall progress</legend>
            <label className="check"><input type="checkbox" checked={draft.computed} onChange={e => setDraft({ ...draft, computed: e.target.checked })} /> Work it out from these weights</label>
            {draft.computed && (
              <>
                <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))" }}>
                  {WEIGHTS.map(w => (
                    <div className="field" key={w.key} style={{ margin: 0 }}>
                      <label htmlFor={`${id}-w-${w.key}`}>{w.label} (%)</label>
                      <input id={`${id}-w-${w.key}`} type="number" inputMode="numeric" min={0} max={100} step={1} required value={draft.weights[w.key]}
                        onChange={e => setDraft({ ...draft, weights: { ...draft.weights, [w.key]: e.target.value } })} />
                    </div>
                  ))}
                </div>
                <p className={total === 100 ? "muted" : "form-error"} aria-live="polite" style={{ margin: 0, fontSize: 13 }}>
                  The weights add up to {total}{total === 100 ? "." : " — they must add up to 100."}
                </p>
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>A part a batch has nothing for yet (say, no assessments) is left out and the others count for more. A trainer can still override one student&apos;s figure, with a reason.</p>
              </>
            )}
          </fieldset>
          {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
          <div className="actions">
            <button type="submit" className="btn small" disabled={saving}>{saving ? "Saving…" : "Save plan"}</button>
            <button type="button" className="btn small ghost" onClick={close} disabled={saving}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
