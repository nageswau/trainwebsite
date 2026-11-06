"use client";
import { useEffect, useId, useState } from "react";

import { type BankQuestion, blankDraft, type Catalogue, choiceList, draftOf, LIMITS, type QuestionDraft, QUESTIONS_URL } from "@/lib/recruiterScreening";

const field = { display: "grid", gap: 4 } as const;

/** The rule shared by a form and a template: what can be told before sending. The API checks again. */
export function questionsProblem(rows: QuestionDraft[]): string | null {
  if (rows.length === 0) return "Add at least one question.";
  if (rows.some((r) => !r.text.trim())) return "Write every question, or remove it.";
  if (rows.some((r) => !r.question_id && r.format === "choice" && choiceList(r.choices).length < 2)) return "Give every choice question at least two choices.";
  return null;
}

/** pob-020: the form builder's rows, used by a requirement's form and by a template. Editing a bank question makes it this form's own. */
export default function RecruiterScreeningQuestions({ rows, catalogue, onChange }: { rows: QuestionDraft[]; catalogue: Catalogue; onChange: (rows: QuestionDraft[]) => void }) {
  const id = useId();
  const [bank, setBank] = useState<BankQuestion[]>([]);
  const [pick, setPick] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${QUESTIONS_URL}?limit=200`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => setBank(Array.isArray(body?.items) ? body.items : []))
      .catch(() => undefined); // only a shortcut: questions can still be written
    return () => controller.abort();
  }, []);

  const update = (key: string, patch: Partial<QuestionDraft>) =>
    onChange(rows.map((r) => {
      if (r.key !== key) return r;
      const next = { ...r, ...patch, question_id: null };
      if (next.format !== "yes_no" || next.category === "compensation") next.is_knockout = false;
      return next;
    }));
  function addFromBank() {
    const question = bank.find((b) => b.id === pick);
    if (!question) return;
    onChange([...rows.filter((r) => r.text.trim()), draftOf(question, true)]);
    setPick("");
  }
  const move = (index: number, by: number) => {
    const next = [...rows];
    const [row] = next.splice(index, 1);
    next.splice(index + by, 0, row);
    onChange(next);
  };

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {rows.map((r, i) => {
        const n = i + 1;
        return (
          <fieldset key={r.key} style={{ border: "1px solid var(--line, #d9dee7)", borderRadius: 8, padding: 10, margin: 0, display: "grid", gap: 8, minWidth: 0 }}>
            <legend style={{ padding: "0 4px", fontSize: 13 }}>Question {n}</legend>
            <label htmlFor={`${id}-${r.key}-text`} style={field}>
              <span className="visually-hidden">Question {n}</span>
              <textarea id={`${id}-${r.key}-text`} aria-label={`Question ${n}`} rows={2} maxLength={LIMITS.text} value={r.text} onChange={(e) => update(r.key, { text: e.target.value })} />
            </label>
            <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
              <label htmlFor={`${id}-${r.key}-category`} style={field}>
                <span>Category<span className="visually-hidden"> for question {n}</span></span>
                <select id={`${id}-${r.key}-category`} value={r.category} onChange={(e) => update(r.key, { category: e.target.value })}>
                  {catalogue.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </label>
              <label htmlFor={`${id}-${r.key}-format`} style={field}>
                <span>Answer format<span className="visually-hidden"> for question {n}</span></span>
                <select id={`${id}-${r.key}-format`} value={r.format} onChange={(e) => update(r.key, { format: e.target.value })}>
                  {catalogue.formats.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select>
              </label>
            </div>
            {r.format === "choice" && (
              <label htmlFor={`${id}-${r.key}-choices`} style={field}>
                <span>Choices, one per line<span className="visually-hidden"> (question {n})</span></span>
                <textarea id={`${id}-${r.key}-choices`} rows={3} value={r.choices} onChange={(e) => update(r.key, { choices: e.target.value })} />
              </label>
            )}
            <label htmlFor={`${id}-${r.key}-criteria`} style={field}>
              <span>What to look for<span className="visually-hidden"> (question {n})</span></span>
              <input id={`${id}-${r.key}-criteria`} maxLength={LIMITS.criteria} value={r.evaluation_criteria} onChange={(e) => update(r.key, { evaluation_criteria: e.target.value })} />
            </label>
            {r.format === "yes_no" && r.category !== "compensation" && (
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={r.is_knockout} onChange={(e) => update(r.key, { is_knockout: e.target.checked, expected_answer: e.target.checked ? (r.expected_answer.trim().toLowerCase() === "no" ? "no" : "yes") : r.expected_answer })} />
                <span>Knock-out<span className="visually-hidden"> (question {n})</span></span>
              </label>
            )}
            {r.is_knockout ? (
              <label htmlFor={`${id}-${r.key}-expected`} style={field}>
                <span>Candidate must answer<span className="visually-hidden"> (question {n})</span></span>
                <select id={`${id}-${r.key}-expected`} value={r.expected_answer === "no" ? "no" : "yes"} onChange={(e) => update(r.key, { expected_answer: e.target.value })}>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
            ) : (
              <label htmlFor={`${id}-${r.key}-expected`} style={field}>
                <span>Expected answer<span className="visually-hidden"> (question {n})</span></span>
                <input id={`${id}-${r.key}-expected`} maxLength={LIMITS.expected} value={r.expected_answer} onChange={(e) => update(r.key, { expected_answer: e.target.value })} />
              </label>
            )}
            <div className="actions" style={{ flexWrap: "wrap" }}>
              <button type="button" className="btn secondary small" disabled={i === 0} onClick={() => move(i, -1)}>Move up<span className="visually-hidden"> question {n}</span></button>
              <button type="button" className="btn secondary small" disabled={i === rows.length - 1} onClick={() => move(i, 1)}>Move down<span className="visually-hidden"> question {n}</span></button>
              <button type="button" className="btn secondary small" onClick={() => onChange(rows.filter((x) => x.key !== r.key))}>Remove<span className="visually-hidden"> question {n}</span></button>
            </div>
          </fieldset>
        );
      })}
      <div className="actions">
        <button type="button" className="btn secondary small" disabled={rows.length >= LIMITS.questions} onClick={() => onChange([...rows, blankDraft()])}>Write a question</button>
      </div>
      {bank.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
          <label htmlFor={`${id}-pick`} style={{ ...field, flex: "1 1 220px", minWidth: 0 }}>Add from the bank
            <select id={`${id}-pick`} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: "100%" }}>
              <option value="">Choose a question</option>
              {bank.map((b) => <option key={b.id} value={b.id}>{b.text}</option>)}
            </select>
          </label>
          <button type="button" className="btn secondary small" disabled={!pick || rows.length >= LIMITS.questions} onClick={addFromBank}>Add from bank</button>
        </div>
      )}
    </div>
  );
}
