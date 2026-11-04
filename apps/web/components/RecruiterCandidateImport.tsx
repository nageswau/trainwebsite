"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import BulkColumnReference from "@/components/BulkColumnReference";
import RecruiterCandidateImportHistory from "@/components/RecruiterCandidateImportHistory";
import { sendRequest } from "@/lib/apiErrors";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import {
  IMPORT_COLUMNS, IMPORT_MAX_BYTES, IMPORT_MAX_ROWS, IMPORTS_URL, PREVIEW_URL, TEMPLATE_URL, previewCounts, reportCounts, reportCsvUrl,
  type CandidateRef, type ImportReport, type Preview,
} from "@/lib/recruiterCandidateImport";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";

const FILE_ID = "candidate-import-file";
const SOURCE_ID = "candidate-import-source";
const NETWORK_ERROR = "The connection dropped. Import again — the same file won't add anyone twice.";
const PREVIEW_LABEL = { new: "New candidate", matched: "Already a candidate", error: "Error" } as const;
const RESULT_LABEL = { created: "Added", matched: "Already a candidate", error: "Error" } as const;

function precheck(file: File | undefined, source: string): string | null {
  if (!file || !source) return "Choose the candidate source and a filled-in .csv or .xlsx file first.";
  if (!/\.(csv|xlsx)$/i.test(file.name)) return "Choose a .csv or .xlsx file.";
  if (file.size > IMPORT_MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function Person({ candidate }: { candidate: CandidateRef | null }) {
  if (!candidate) return <>-</>;
  return (
    <>
      <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(candidate.id)}`}>{candidate.candidate_code}</Link>
      <span className="muted" style={{ overflowWrap: "anywhere" }}> {candidate.name}</span>
    </>
  );
}

function PreviewTable({ preview }: { preview: Preview }) {
  return (
    <div className="table-wrap">
      <table className="table bulk-report" aria-label="Rows in this file">
        <thead>
          <tr><th>Row</th><th>Name in the file</th><th>Check</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {preview.rows.map((r) => (
            <tr key={r.row_number}>
              <td data-label="Row">{r.row_number}</td>
              <td data-label="Name in the file" style={{ overflowWrap: "anywhere" }}>{r.name || "-"}</td>
              <td data-label="Check">{PREVIEW_LABEL[r.status]}</td>
              <td data-label="Detail">{r.candidate ? <Person candidate={r.candidate} /> : r.reason ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ImportResult({ report }: { report: ImportReport }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [report]);
  const tone = report.error_count ? "form-warning" : "form-message";
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Import result</h4>
      <p className={tone}>
        {reportCounts(report)}.{report.replayed ? " This file was already imported, so nothing new was added." : ""}
        {report.error_count ? " Fix the rows with errors and import just those." : ""}
      </p>
      <p><a className="btn secondary small" href={reportCsvUrl(report.id)} download>Download the full report (.csv)</a></p>
      <div className="table-wrap">
        <table className="table bulk-report" aria-label="Import report">
          <thead>
            <tr><th>Row</th><th>Result</th><th>Candidate</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row_number}>
                <td data-label="Row">{r.row_number}</td>
                <td data-label="Result">{RESULT_LABEL[r.status]}</td>
                <td data-label="Candidate"><Person candidate={r.candidate} /></td>
                <td data-label="Detail">{r.reason ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// hrc-013 (DEC-SCOPE-391 I12): 1 template, 2 source + file -> Check file (read only), 3 the preview -> Import, 4 the report. The
// Idempotency-Key belongs to the chosen file and source: a retry after a dropped connection replays the first result.
export default function RecruiterCandidateImport() {
  const [sources, setSources] = useState<CatalogueValue[] | null>(null);
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"" | "check" | "import">("");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const inFlight = useRef(false); // `busy` disables the buttons only after a re-render; a double click must not send twice
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => controller.signal.aborted || setSourcesFailed(true));
    return () => controller.abort();
  }, []);

  function changed(next: { file?: File | null; source?: string }) {
    if (next.file !== undefined) setFile(next.file);
    if (next.source !== undefined) setSource(next.source);
    setKey(newIdempotencyKey());
    setPreview(null);
    setError("");
  }

  function reset() {
    changed({ file: null });
    if (input.current) input.current.value = "";
    input.current?.focus();
  }

  async function send(url: string, kind: "check" | "import", headers?: Record<string, string>) {
    if (inFlight.current || !file) return null;
    inFlight.current = true;
    setBusy(kind);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("source_id", source);
    const outcome = await sendRequest(url, { method: "POST", headers, body });
    inFlight.current = false;
    setBusy("");
    if (!outcome.ok) {
      setError(outcome.status ? outcome.message : kind === "import" ? NETWORK_ERROR : "The connection dropped. Check the file again.");
      return null;
    }
    return outcome.data;
  }

  async function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = precheck(file ?? undefined, source);
    if (problem) return setError(problem);
    setReport(null);
    const data = await send(PREVIEW_URL, "check");
    if (data) setPreview(data as Preview);
  }

  async function commit() {
    const data = await send(IMPORTS_URL, "import", { "Idempotency-Key": key });
    if (!data) return;
    setReport(data as ImportReport);
    setPreview(null);
    setFile(null);
    if (input.current) input.current.value = "";
    setVersion((v) => v + 1);
  }

  const fresh = preview?.new_count ?? 0;
  return (
    <>
      <div className="action-card lead-import">
        <h3>Import candidates (CSV or Excel)</h3>
        <p className="muted">
          Add many candidates in one go. Each row is checked like a manual add, and a mobile number or email that is already in the candidate
          master is matched to that candidate — it is never added twice and the existing record is not changed. Nothing is saved until you
          check the file and press Import.
        </p>
        <form className="form" onSubmit={check} aria-busy={busy !== ""} noValidate>
          <h4>1. Download the template</h4>
          <a className="btn secondary" href={TEMPLATE_URL} download>Download the template (.csv)</a>
          <BulkColumnReference columns={IMPORT_COLUMNS} />
          <h4 style={{ marginTop: 16 }}>2. Choose the source and the filled-in file</h4>
          <div className="field">
            <label htmlFor={SOURCE_ID}>Candidate source</label>
            <select id={SOURCE_ID} value={source} onChange={(e) => changed({ source: e.target.value })} disabled={busy !== "" || !sources}>
              <option value="">{sources ? "Choose a source" : "Loading sources…"}</option>
              {sources?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {sourcesFailed && <p className="form-error">Sources could not be loaded. Reload the page to try again.</p>}
          </div>
          <div className="field">
            <label htmlFor={FILE_ID}>Filled-in candidates file</label>
            <input ref={input} id={FILE_ID} type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e: ChangeEvent<HTMLInputElement>) => changed({ file: e.target.files?.[0] ?? null })} disabled={busy !== ""} aria-describedby={`${FILE_ID}-help`} />
            <p id={`${FILE_ID}-help`} className="muted field-help">
              CSV (UTF-8) or Excel (.xlsx), up to 1 MB and {IMPORT_MAX_ROWS.toLocaleString("en-IN")} candidates. One candidate per row; a name and a mobile or an email are required.
            </p>
          </div>
          <button className="btn" disabled={busy !== ""}>{busy === "check" ? "Checking…" : "Check file"}</button>
        </form>
        <p className="visually-hidden" role="status" aria-live="polite">
          {busy === "check" ? "Checking every row." : busy === "import" ? "Importing — checking each row for duplicates." : ""}
        </p>
        {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
        {preview && (
          <div style={{ marginTop: 16 }}>
            <h4>3. Check the rows</h4>
            <p>{previewCounts(preview)}.</p>
            {fresh === 0 && <p className="form-warning">Nothing new to add — every row is already a candidate or has an error.</p>}
            <PreviewTable preview={preview} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
              {fresh > 0 && (
                <button type="button" className="btn" onClick={commit} disabled={busy !== ""}>
                  {busy === "import" ? "Importing…" : `Import ${fresh.toLocaleString("en-IN")} new candidate${fresh === 1 ? "" : "s"}`}
                </button>
              )}
              <button type="button" className="btn secondary" onClick={reset} disabled={busy !== ""}>Choose another file</button>
            </div>
          </div>
        )}
        {report && <ImportResult report={report} />}
      </div>
      <RecruiterCandidateImportHistory version={version} />
    </>
  );
}
