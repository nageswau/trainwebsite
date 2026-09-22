"use client";

import { type FormEvent, useState } from "react";

import SchoolSkillAlert from "@/components/SchoolSkillAlert";
import { SkillStatus, useSkillAction } from "@/components/useSkillAction";
import { canMark, type SkillAssessment, type SkillBatchDetail } from "@/lib/skills";

// ENH-011 spec §7: several assessments per batch (D8), each with a score grid labelled "Score for <student> (out of <max>)" and an
// optional remark (§9 "improvement required"). A score outside 0..max is caught on its field before anything is sent. Read-only on a
// closed batch.
const BASE = "/api/v1/school/career-counselor";
type Action = ReturnType<typeof useSkillAction>;

export default function SchoolSkillScores({ batch }: { batch: SkillBatchDetail }) {
  const action = useSkillAction();
  const [name, setName] = useState("");
  const [max, setMax] = useState("");
  const [selectedId, setSelectedId] = useState(batch.assessments.at(-1)?.id ?? "");
  const assessment = batch.assessments.find((a) => a.id === selectedId) ?? batch.assessments.at(-1);
  const open = batch.status === "open";

  async function addAssessment(e: FormEvent) {
    e.preventDefault();
    const created = await action.run<SkillAssessment>(`${BASE}/skill-batches/${batch.id}/assessments`, "POST", { name, max_score: Number(max) }, (a) => `${a.name} added.`);
    if (created) {
      setName("");
      setMax("");
      setSelectedId(created.id);
    }
  }

  return (
    <div className="card" aria-busy={action.busy}>
      <h2>Assessments and scores</h2>
      <SkillStatus message={action.message} />
      <SchoolSkillAlert alert={action.alert} />
      {open && (
        <form className="form" onSubmit={addAssessment}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="skill-assessment-name">Assessment name</label>
              <input id="skill-assessment-name" className="search" required maxLength={120} value={name} disabled={action.busy} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="skill-assessment-max">Maximum score</label>
              <input id="skill-assessment-max" type="number" inputMode="decimal" className="search" required min={0.01} max={1000} step={0.01} value={max} disabled={action.busy} onChange={(e) => setMax(e.target.value)} />
            </div>
          </div>
          <button type="submit" className="btn secondary small" disabled={action.busy || !name.trim() || !max}>Add assessment</button>
        </form>
      )}
      {!assessment ? (
        <p className="muted">No assessments yet. Add one to record scores.</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="skill-assessment-pick">Assessment</label>
            <select id="skill-assessment-pick" className="select" value={assessment.id} onChange={(e) => setSelectedId(e.target.value)}>
              {batch.assessments.map((a) => <option key={a.id} value={a.id}>{`${a.name} (out of ${a.max_score})`}</option>)}
            </select>
          </div>
          {open ? (
            <ScoreGrid key={`${assessment.id}:${JSON.stringify(batch.enrollments.map((e) => e.scores))}`} batch={batch} assessment={assessment} action={action} />
          ) : (
            <ul>
              {batch.enrollments.map((e) => {
                const s = e.scores.find((x) => x.assessment_id === assessment.id);
                return <li key={e.id}>{s ? `${e.student_name}: ${s.score} / ${assessment.max_score}${s.remarks ? ` (${s.remarks})` : ""}` : `${e.student_name}: not scored`}</li>;
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function ScoreGrid({ batch, assessment, action }: { batch: SkillBatchDetail; assessment: SkillAssessment; action: Action }) {
  const markable = batch.enrollments.filter(canMark);
  const [values, setValues] = useState<Record<string, { score: string; remarks: string }>>(() =>
    Object.fromEntries(markable.map((e) => {
      const s = e.scores.find((x) => x.assessment_id === assessment.id);
      return [e.id, { score: s ? String(s.score) : "", remarks: s?.remarks ?? "" }];
    })),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const entered = markable.filter((e) => values[e.id].score.trim() !== "");

  function save(ev: FormEvent) {
    ev.preventDefault();
    const found: Record<string, string> = {};
    for (const e of entered) {
      const n = Number(values[e.id].score);
      if (!Number.isFinite(n) || n < 0 || n > assessment.max_score) found[e.id] = `Enter a score from 0 to ${assessment.max_score}`;
    }
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const scores = entered.map((e) => ({ enrollment_id: e.id, score: Number(values[e.id].score), remarks: values[e.id].remarks.trim() || null }));
    void action.run(`${BASE}/skill-assessments/${assessment.id}/scores`, "PUT", { scores }, () => `Scores saved for ${assessment.name}.`);
  }

  const set = (id: string, field: "score" | "remarks") => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [id]: { ...v[id], [field]: e.target.value } }));
  if (markable.length === 0) return <p className="muted">No student in this batch can be scored: they are certified, withdrawn or have moved school.</p>;
  return (
    <form className="form" onSubmit={save} noValidate>
      <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <legend>Scores for {assessment.name} (out of {assessment.max_score})</legend>
        {markable.map((e) => (
          <div key={e.id} className="form-grid">
            <div className="field">
              <label htmlFor={`skill-score-${e.id}`}>{`Score for ${e.student_name} (out of ${assessment.max_score})`}</label>
              <input id={`skill-score-${e.id}`} type="number" inputMode="decimal" className="search" min={0} max={assessment.max_score} step={0.01} value={values[e.id].score} disabled={action.busy}
                aria-invalid={errors[e.id] ? true : undefined} aria-describedby={errors[e.id] ? `skill-score-${e.id}-error` : undefined} onChange={set(e.id, "score")} />
              {errors[e.id] && <span id={`skill-score-${e.id}-error`} className="form-error">{errors[e.id]}</span>}
            </div>
            <div className="field">
              <label htmlFor={`skill-remarks-${e.id}`}>{`Remarks for ${e.student_name} (optional)`}</label>
              <input id={`skill-remarks-${e.id}`} className="search" maxLength={2000} value={values[e.id].remarks} disabled={action.busy} onChange={set(e.id, "remarks")} />
            </div>
          </div>
        ))}
      </fieldset>
      <button type="submit" className="btn small" disabled={action.busy || entered.length === 0}>{action.busy ? "Saving…" : "Save scores"}</button>
    </form>
  );
}
