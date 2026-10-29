"use client";

import { useRef, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";

// nehn-025: the trainer's "Import questions from Excel" card. Upload the filled template -> the server checks every row (a dry run) ->
// preview with per-row errors -> import, offered only when every row is valid (the server re-checks the same file and writes all or none).
const BASE = "/api/v1/workflows/it/trainer/assessments";
const TYPE_LABEL: Record<string, string> = { mcq_single: "Single choice", mcq_multiple: "Multiple choice", text: "Written answer", file: "File response" };

type ImportAssessment = { id: string; title: string; batch: string; status: string; attempt_count: number };
type PreviewQuestion = { row: number; question_type: string; prompt: string; options: string[]; correct_answers: string[]; max_score: number };
type RowNote = { row: number | null; message: string };
type Preview = { total_rows: number; questions: PreviewQuestion[]; errors: RowNote[]; warnings: RowNote[]; created: number };
type Props = { assessments: ImportAssessment[]; loading: boolean; onImported: () => void | Promise<void> };

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

export default function QuestionImportPanel({ assessments, loading, onImported }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [assessmentId, setAssessmentId] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const title = assessments.find(item => item.id === assessmentId)?.title ?? "";

  function reset() {
    setPreview(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function send(commit: boolean) {
    const file = fileInput.current?.files?.[0];
    if (!assessmentId || !file) return setMessage({ text: "Choose an assessment and a filled template first.", failed: true });
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    const outcome = await sendRequest(`${BASE}/${assessmentId}/questions/import${commit ? "?commit=true" : ""}`, { method: "POST", body: form });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    const result = outcome.data as Preview;
    if (!commit) return setPreview(result);
    reset();
    setMessage({ text: `${plural(result.created, "question")} imported into ${title}. A Draft stays hidden from students until you publish it in Edit assessment.`, failed: false });
    await onImported();
  }

  const ready = preview && !preview.errors.length && preview.questions.length > 0;
  return (
    <div className="action-card question-import">
      <h3>Import questions from Excel</h3>
      <p className="muted">Fill in the standard template, check it, then import every question in one step.</p>
      <p><a className="btn secondary small" href={`${BASE}/question-template.xlsx`} download>Download the question template</a></p>
      {message && <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</div>}
      <form className="form" noValidate onSubmit={event => { event.preventDefault(); void send(false); }}>
        <div className="field">
          <label htmlFor="question-import-assessment">Assessment to fill</label>
          <select id="question-import-assessment" value={assessmentId} onChange={event => { setAssessmentId(event.target.value); setPreview(null); }}>
            <option value="">Select assessment</option>
            {assessments.map(item => <option key={item.id} value={item.id} disabled={item.attempt_count > 0}>{item.title} · {item.batch} · {item.status}{item.attempt_count > 0 ? " · locked, already attempted" : ""}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="question-import-file">Filled template (.xlsx or .csv)</label>
          <input id="question-import-file" ref={fileInput} type="file" accept=".xlsx,.csv" onChange={() => setPreview(null)} />
        </div>
        {!assessments.length && <p className="muted">{loading ? "Loading assessments…" : "Create an assessment before importing questions."}</p>}
        <button className="btn" disabled={busy || loading}>{busy && !preview ? "Checking…" : "Check file"}</button>
      </form>
      {preview && (
        <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
          <p role="status" style={{ margin: 0 }}>
            {preview.errors.length
              ? `${preview.errors.length} of ${plural(preview.total_rows, "row")} ${preview.errors.length === 1 ? "has" : "have"} errors. Fix them in the file and check it again -- nothing is imported until every row is valid.`
              : `${plural(preview.questions.length, "question")} ${preview.questions.length === 1 ? "is" : "are"} ready to import into ${title}.`}
          </p>
          {preview.errors.length > 0 && (
            <div className="table-wrap">
              <table className="table compact stack" aria-label="Rows with errors">
                <thead><tr><th>Row</th><th>Problem</th></tr></thead>
                <tbody>{preview.errors.map(item => <tr key={item.row}><td data-label="Row">{item.row}</td><td data-label="Problem">{item.message}</td></tr>)}</tbody>
              </table>
            </div>
          )}
          {preview.warnings.length > 0 && (
            <ul className="muted" style={{ margin: 0, paddingLeft: 20 }}>
              {preview.warnings.map(item => <li key={`${item.row}-${item.message}`}>{item.row ? `Row ${item.row}: ` : ""}{item.message}</li>)}
            </ul>
          )}
          {preview.questions.length > 0 && (
            <div className="table-wrap">
              <table className="table compact stack" aria-label="Questions in the file">
                <thead><tr><th>Row</th><th>Type</th><th>Question</th><th>Options</th><th>Correct</th><th>Marks</th></tr></thead>
                <tbody>
                  {preview.questions.map(item => (
                    <tr key={item.row}>
                      <td data-label="Row">{item.row}</td>
                      <td data-label="Type">{TYPE_LABEL[item.question_type] ?? item.question_type}</td>
                      <td data-label="Question" style={{ whiteSpace: "pre-wrap" }}>{item.prompt}</td>
                      <td data-label="Options">{item.options.map((option, index) => `${index + 1}. ${option}`).join(" · ")}</td>
                      <td data-label="Correct">{item.correct_answers.join(", ")}</td>
                      <td data-label="Marks">{item.max_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {ready && <button type="button" className="btn" disabled={busy} onClick={() => void send(true)}>{busy ? "Importing…" : `Import ${plural(preview.questions.length, "question")}`}</button>}
            <button type="button" className="btn secondary" disabled={busy} onClick={() => { reset(); setMessage(null); }}>Choose another file</button>
          </div>
        </div>
      )}
    </div>
  );
}
