"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import BulkColumnReference from "@/components/BulkColumnReference";
import UniversityImportHistory from "@/components/UniversityImportHistory";
import { detailMessage } from "@/lib/apiErrors";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { IMPORT_COLUMNS, IMPORT_MAX_BYTES, IMPORT_MAX_ROWS, IMPORT_TEMPLATE_URL, IMPORT_URL, RESULT_LABEL, importCounts, reportCsvUrl, type ImportReport } from "@/lib/universityImport";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FILE_ID = "university-import-file";
const NETWORK_ERROR = "The connection dropped. Import again — the same file won't be added twice.";
const BUSY_MESSAGE = "Importing — checking each row for duplicates.";

function precheck(file: File | undefined): string | null {
  if (!file) return "Choose a filled-in CSV file first.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size > IMPORT_MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function summary(report: ImportReport): Feedback {
  if (report.created_count === 0) return { text: `No universities were added (${importCounts(report)}). Check the rows below.`, tone: "error" };
  if (report.created_count === report.total_rows) return { text: `${importCounts(report)}.`, tone: "success" };
  return { text: `${importCounts(report)}. Fix the invalid rows and upload just those; duplicates are already in the master.`, tone: "warning" };
}

function ImportResult({ report }: { report: ImportReport }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [report]);
  const note = summary(report);
  const skipped = report.rows.filter((r) => r.status !== "created");
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Import result</h4>
      <p className={toneClass[note.tone]}>{note.text}</p>
      <p>
        <a className="btn secondary small" href={reportCsvUrl(report.id)} download>Download the full report (.csv)</a>
      </p>
      {skipped.length > 0 && (
        <div className="table-wrap">
          <table className="table bulk-report" aria-label="Rows not created">
            <thead>
              <tr><th>Row</th><th>Name</th><th>Country</th><th>Result</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {skipped.map((r) => (
                <tr key={r.row_number}>
                  <td data-label="Row">{r.row_number}</td>
                  <td data-label="Name">{r.name || "-"}</td>
                  <td data-label="Country">{r.country || "-"}</td>
                  <td data-label="Result">{RESULT_LABEL[r.status]}</td>
                  <td data-label="Detail">{r.reason ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// upc-005 (IM12): download the template, upload; each row is created (unowned, internal), a duplicate (upc-004's key) or invalid. The
// Idempotency-Key belongs to the chosen file: a retry after a dropped connection replays the first result instead of importing twice.
export default function UniversityImportPanel() {
  const [chosen, setChosen] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [version, setVersion] = useState(0);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not upload twice
  const input = useRef<HTMLInputElement>(null);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setChosen(file ? { file, key: newIdempotencyKey() } : null);
    setError(null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const problem = precheck(chosen?.file);
    if (problem || !chosen) {
      setError(problem);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", chosen.file);
    try {
      const response = await fetch(IMPORT_URL, { method: "POST", headers: { "Idempotency-Key": chosen.key }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(detailMessage(data.detail, "Unable to import this file."));
        return;
      }
      setReport(data);
      setChosen(null);
      if (input.current) input.current.value = "";
      setVersion((v) => v + 1);
    } catch {
      setError(NETWORK_ERROR);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <div className="action-card lead-import">
        <h3>Import universities (CSV)</h3>
        <p className="muted">
          Add many universities in one go. Each row is checked like a manual add: a name already in the master for that country is reported as a
          duplicate, never added twice. Imported universities are unassigned and internal until someone assigns and publishes them.
        </p>
        <form className="form" onSubmit={upload} aria-busy={busy} noValidate>
          <h4>1. Download the template</h4>
          <a className="btn secondary" href={IMPORT_TEMPLATE_URL} download>Download the template (.csv)</a>
          <BulkColumnReference columns={IMPORT_COLUMNS} />
          <h4 style={{ marginTop: 16 }}>2. Upload the filled-in file</h4>
          <div className="field">
            <label htmlFor={FILE_ID}>Filled-in universities file</label>
            <input ref={input} id={FILE_ID} type="file" accept=".csv,text/csv" onChange={chooseFile} disabled={busy} aria-describedby={`${FILE_ID}-help`} />
            <p id={`${FILE_ID}-help`} className="muted field-help">
              CSV, up to 1 MB and {IMPORT_MAX_ROWS.toLocaleString("en-IN")} universities. One university per row; name, country, city and institution type are required.
            </p>
          </div>
          <button className="btn" disabled={busy}>{busy ? "Importing…" : "Import universities"}</button>
        </form>
        <p className="visually-hidden" role="status" aria-live="polite">{busy ? BUSY_MESSAGE : ""}</p>
        {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
        {report && <ImportResult report={report} />}
      </div>
      <UniversityImportHistory version={version} />
    </>
  );
}
