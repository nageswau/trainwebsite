"use client";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterScreeningQuestions, { questionsProblem } from "@/components/RecruiterScreeningQuestions";
import { sendJson } from "@/lib/apiErrors";
import { type Comparison, comparisonUrl, draftBody, draftOf, type FormRead, formUrl, isComparison, isFormRead, type QuestionDraft, scoreText, type ScreeningForm, yesNoLabel } from "@/lib/recruiterScreening";

const small = { margin: 0, fontSize: 13 } as const;

function FormView({ form }: { form: ScreeningForm }) {
  return (
    <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6, fontSize: 14 }}>
      {form.questions.map((q) => (
        <li key={q.id} style={{ overflowWrap: "anywhere" }}>
          <span>{q.text}</span>
          {q.is_knockout && <span className="badge" style={{ marginLeft: 6 }}>Knock-out</span>}
          <div className="muted" style={{ fontSize: 12 }}>
            {q.category_label} · {q.format_label}{q.evaluation_criteria && <> · Look for: {q.evaluation_criteria}</>}
            {q.expected_answer && <> · Expected: {q.is_knockout ? yesNoLabel(q.expected_answer) : q.expected_answer}</>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** AC4: each candidate's latest session on one form version, best score first. A stacked table on a phone. */
function ComparisonTable({ requirementId, current }: { requirementId: string; current: number }) {
  const [version, setVersion] = useState(current);
  const [data, setData] = useState<Comparison | null>(null);
  const [failed, setFailed] = useState(false);
  const id = useId();

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(comparisonUrl(requirementId, version === current ? undefined : version), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isComparison(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requirementId, version, current]);

  if (failed) return <p className="form-error" role="alert" style={small}>Unable to load the comparison.</p>;
  if (data === null) return <p className="muted" role="status" style={small}>Loading comparison…</p>;
  return (
    <div style={{ display: "grid", gap: 8, gridTemplateColumns: "minmax(0, 1fr)" }}>
      {data.versions.length > 1 && (
        <label htmlFor={`${id}-version`} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
          Form version
          <select id={`${id}-version`} value={version} onChange={(e) => setVersion(Number(e.target.value))}>
            {data.versions.map((v) => <option key={v} value={v}>{v}{v === current ? " (current)" : ""}</option>)}
          </select>
        </label>
      )}
      {data.rows.length === 0 ? (
        <p className="muted" style={small}>No candidate has been screened on this form version.</p>
      ) : (
        <>
        <ul aria-label="Questions compared" style={{ margin: 0, padding: 0, listStyle: "none", fontSize: 13, display: "grid", gap: 2 }}>
          {data.questions.map((q, i) => <li key={q.id} style={{ overflowWrap: "anywhere" }}><strong>Q{i + 1}</strong> {q.text}</li>)}
        </ul>
        <div style={{ overflowX: "auto" }}>
          <table className="table stack screening-comparison" aria-label={`Screening comparison, form version ${data.version}`}>
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Score</th>
                <th scope="col">Recommendation</th>
                {data.questions.map((q, i) => <th key={q.id} scope="col" title={q.text}>Q{i + 1}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.application_id}>
                  <td data-label="Candidate" style={{ overflowWrap: "anywhere" }}>
                    <div>
                      <strong>{row.candidate.name}</strong>
                      <div className="muted" style={{ fontSize: 12 }}>{row.status_label} · <LocalTime value={row.created_at} /></div>
                    </div>
                  </td>
                  <td data-label="Score">{scoreText(row.scorecard)}</td>
                  <td data-label="Recommendation">
                    <div>
                      {row.recommendation_label}
                      {row.knockout_triggered && <div className="muted" style={{ fontSize: 12 }}>{row.knockout_overridden ? "Knock-out overridden" : "Knock-out failed"}</div>}
                    </div>
                  </td>
                  {data.questions.map((q, i) => {
                    const cell = row.answers[q.id];
                    return (
                      <td key={q.id} data-label={`Q${i + 1}`} style={{ overflowWrap: "anywhere" }}>
                        {!cell ? <span className="muted">—</span> : (
                          <div>
                            {cell.score !== null && <div>{cell.score} / 5</div>}
                            <div className="muted" style={{ fontSize: 12 }}>{cell.answer_hidden ? "Hidden" : q.format === "yes_no" ? yesNoLabel(cell.answer) : cell.answer}</div>
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}
      {data.truncated && <p className="muted" style={small}>Showing the 50 most recently screened candidates.</p>}
    </div>
  );
}

/** pob-020 (DEC-SCOPE-412): the requirement's form -- create from a template, tailor into a new version, a Team Lead's knock-out approval,
 *  and the comparison. Opened on demand so a requirement page that doesn't need it pays nothing. */
export default function RecruiterScreeningForm({ requirementId }: { requirementId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<FormRead | null>(null);
  const [failed, setFailed] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [rows, setRows] = useState<QuestionDraft[] | null>(null);
  const [comparing, setComparing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const sending = useRef(false);
  const id = useId();

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(formUrl(requirementId), { signal });
      const body = response.ok ? await response.json() : null;
      if (isFormRead(body)) setData(body);
      else setFailed(true);
    } catch {
      if (!signal?.aborted) setFailed(true);
    }
  }, [requirementId]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [open, load]);

  async function send(url: string, method: "POST" | "PUT", body: unknown, done: (form: ScreeningForm | null) => string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    const outcome = await sendJson(url, method, body);
    sending.current = false;
    setBusy(false);
    if (outcome.ok) {
      setNotice(done((outcome.data.form as ScreeningForm | undefined) ?? null));
      setRows(null);
    } else {
      setFailure(outcome.message);
    }
    await load();
  }

  function save() {
    const problem = questionsProblem(rows ?? []);
    if (problem) return setFailure(problem);
    void send(formUrl(requirementId), "PUT", { questions: (rows ?? []).map(draftBody) }, (form) => `Saved as version ${form?.version}.`);
  }

  const form = data?.form ?? null;
  return (
    <section className="action-card wide" aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} style={{ margin: 0 }}>Screening form</h3>
      <div className="actions">
        <button type="button" className="btn secondary small" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{open ? "Hide screening form" : "Show screening form"}</button>
      </div>
      {open && failed && <p className="form-error" role="alert" style={small}>Unable to load the screening form.</p>}
      {open && !failed && data === null && <p className="muted" role="status" style={small}>Loading screening form…</p>}
      {open && data && (
        <div style={{ display: "grid", gap: 10 }}>
          {notice && <p role="status" style={small}>{notice}</p>}
          {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
          {form === null ? (
            <>
              <p className="muted" style={small}>This requirement has no screening form yet.</p>
              {data.can_edit && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
                  <label htmlFor={`${id}-template`} style={{ display: "grid", gap: 4 }}>
                    Template
                    <select id={`${id}-template`} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                      <option value="">Default ({data.templates.find((t) => t.is_default)?.name ?? "standard"})</option>
                      {data.templates.filter((t) => !t.is_default).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </label>
                  <button type="button" className="btn small" disabled={busy} onClick={() => void send(formUrl(requirementId), "POST", templateId ? { template_id: templateId } : {}, () => "Screening form created.")}>
                    {busy ? "Creating…" : "Create form"}
                  </button>
                </div>
              )}
            </>
          ) : rows ? (
            <>
              <RecruiterScreeningQuestions rows={rows} catalogue={data} onChange={setRows} />
              <p className="muted" style={small}>Earlier sessions keep the version they answered. Changing a knock-out needs a Team Lead&apos;s approval again.</p>
              <div className="actions">
                <button type="button" className="btn small" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save new version"}</button>
                <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setRows(null); setFailure(null); }}>Cancel</button>
              </div>
            </>
          ) : (
            <>
              <p style={small}><strong>{form.name}</strong> <span className="muted">· version {form.version}</span></p>
              {form.knockout_status !== "none" && (
                <p style={small}>
                  <span className={form.knockout_status === "pending" ? "badge badge-pending" : "badge"}>{form.knockout_status_label}</span>
                  {form.knockout_approved_by && form.knockout_approved_at && <span className="muted"> by {form.knockout_approved_by.full_name} on <LocalTime value={form.knockout_approved_at} /></span>}
                </p>
              )}
              <FormView form={form} />
              <div className="actions" style={{ flexWrap: "wrap" }}>
                {data.can_edit && <button type="button" className="btn secondary small" onClick={() => { setRows(form.questions.map((q) => draftOf(q))); setNotice(null); setFailure(null); }}>Edit questions</button>}
                {data.can_approve && form.knockout_status === "pending" && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => void send(formUrl(requirementId, "/approve-knockouts"), "POST", { version: form.version }, () => "Knock-outs approved.")}>Approve knock-outs</button>
                )}
                <button type="button" className="btn secondary small" aria-expanded={comparing} onClick={() => setComparing((v) => !v)}>Compare candidates</button>
              </div>
              {comparing && <ComparisonTable key={form.version} requirementId={requirementId} current={form.version} />}
            </>
          )}
        </div>
      )}
    </section>
  );
}
