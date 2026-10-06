"use client";
import type { ScriptStep } from "@/lib/telecallerContent";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

export type StepDraft = { key: number; title: string; notes: string };
export const MAX_STEPS = 20;

let nextKey = 0;
export const draftStep = (step: ScriptStep = { title: "", notes: null }): StepDraft => ({ key: nextKey++, title: step.title, notes: step.notes ?? "" });
export const stepsBody = (steps: StepDraft[]): ScriptStep[] => steps.map((s) => ({ title: s.title.trim(), notes: s.notes.trim() || null }));

// tel-012 (C3): a script's ordered steps -- a title (required) and optional talking points each; add, remove, move up/down; 1-20 steps
// (the API re-checks). Controlled: the form that owns it posts `stepsBody(steps)`.
export default function TelecallerScriptSteps({ idPrefix, steps, onChange, disabled }: { idPrefix: string; steps: StepDraft[]; onChange: (steps: StepDraft[]) => void; disabled?: boolean }) {
  const focus = useFocusAfterRender();
  const id = (part: string, key: number) => `${idPrefix}-${part}-${key}`;
  const set = (index: number, patch: Partial<StepDraft>) => onChange(steps.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  // QA-02: keyboard focus stays with the step -- on the same move button, or the other one once that end is reached.
  function move(index: number, by: number) {
    const next = [...steps];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    onChange(next);
    const [same, other] = by < 0 ? ["up", "down"] : ["down", "up"];
    const atEnd = by < 0 ? index + by === 0 : index + by === steps.length - 1;
    focus(id(atEnd ? other : same, steps[index].key));
  }
  function add() {
    const step = draftStep();
    onChange([...steps, step]);
    focus(id("title", step.key));
  }
  function remove(index: number) {
    onChange(steps.filter((_, j) => j !== index));
    focus(id("title", (steps[index + 1] ?? steps[index - 1]).key));
  }

  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontWeight: 800, fontSize: 13, marginBottom: 7 }}>Steps (required, in order)</legend>
      <ol style={{ paddingLeft: 20, display: "grid", gap: 12 }}>
        {steps.map((step, i) => (
          <li key={step.key}>
            <div className="field">
              <label htmlFor={id("title", step.key)}>Step {i + 1} title</label>
              <input id={id("title", step.key)} value={step.title} onChange={(e) => set(i, { title: e.target.value })} required maxLength={120} disabled={disabled} />
            </div>
            <div className="field">
              <label htmlFor={id("notes", step.key)}>Step {i + 1} talking points</label>
              <textarea id={id("notes", step.key)} value={step.notes} onChange={(e) => set(i, { notes: e.target.value })} maxLength={1000} rows={2} disabled={disabled} />
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button id={id("up", step.key)} type="button" className="btn secondary small" aria-label={`Move step ${i + 1} up`} onClick={() => move(i, -1)} disabled={disabled || i === 0}>Up</button>
              <button id={id("down", step.key)} type="button" className="btn secondary small" aria-label={`Move step ${i + 1} down`} onClick={() => move(i, 1)} disabled={disabled || i === steps.length - 1}>Down</button>
              <button type="button" className="btn secondary small" aria-label={`Remove step ${i + 1}`} onClick={() => remove(i)} disabled={disabled || steps.length === 1}>Remove</button>
            </div>
          </li>
        ))}
      </ol>
      <button type="button" className="btn secondary small" onClick={add} disabled={disabled || steps.length >= MAX_STEPS}>Add step</button>
      {steps.length >= MAX_STEPS && <p className="muted" style={{ fontSize: 13 }}>A script has at most {MAX_STEPS} steps.</p>}
    </fieldset>
  );
}
