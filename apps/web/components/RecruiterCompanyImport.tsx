"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import BulkColumnReference from "@/components/BulkColumnReference";
import LocalTime from "@/components/LocalTime";
import { sendRequest, type Page } from "@/lib/apiErrors";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";
import {
  IMPORT_COLUMNS, IMPORT_MAX_BYTES, IMPORT_MAX_ROWS, IMPORTS_URL, PREVIEW_URL, TEMPLATE_URL, previewCounts, reportCounts, reportCsvUrl,
  type CompanyRef, type ContactRef, type ImportReport, type ImportSummary, type Preview,
} from "@/lib/recruiterCompanyImport";
import { getPage } from "@/lib/telecallerCatalogue";

const FILE_ID = "company-import-file";
const NETWORK_ERROR = "The connection dropped. Import again — the same file won't add anything twice.";
const OUTCOME: Record<string, string> = { new: "New", created: "Added", matched: "Already here" };

function precheck(file: File | null): string | null {
  if (!file) return "Choose a filled-in .csv or .xlsx file first.";
  if (!/\.(csv|xlsx)$/i.test(file.name)) return "Choose a .csv or .xlsx file.";
  if (file.size > IMPORT_MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function CompanyCell({ company, fallback }: { company: CompanyRef | null; fallback?: string }) {
  if (!company) return <span style={{ overflowWrap: "anywhere" }}>{fallback || "-"}</span>;
  return (
    <span style={{ overflowWrap: "anywhere" }}>
      {company.in_scope ? <Link href={`${COMPANIES_PATH}/${encodeURIComponent(company.id)}`}>{company.code}</Link> : company.code} {company.name}
    </span>
  );
}

const contactText = (contact: ContactRef | null, fallback?: string) => contact?.name || fallback || "-";

function PreviewTable({ preview }: { preview: Preview }) {
  return (
    <div className="table-wrap">
      <table className="table stack bulk-report" aria-label="Rows in this file">
        <thead>
          <tr><th>Row</th><th>Company</th><th>Contact</th><th>Check</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {preview.rows.map((r) => (
            <tr key={r.row_number}>
              <td data-label="Row">{r.row_number}</td>
              <td data-label="Company"><CompanyCell company={r.company} fallback={r.company_name} /></td>
              <td data-label="Contact" style={{ overflowWrap: "anywhere" }}>{contactText(r.contact, r.contact_name)}</td>
              <td data-label="Check">
                {r.status === "error" ? "Error" : `Company: ${OUTCOME[r.company_outcome ?? ""] ?? "-"}${r.contact_outcome ? `. Contact: ${OUTCOME[r.contact_outcome]}` : ""}`}
              </td>
              <td data-label="Detail">{r.reason ?? "-"}</td>
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
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Import result</h4>
      <p className={report.error_count ? "form-warning" : "form-message"}>
        {reportCounts(report)}.{report.replayed ? " This file was already imported, so nothing new was added." : ""}
        {report.error_count ? " Fix the rows with errors and import just those." : ""}
      </p>
      <p><a className="btn secondary small" href={reportCsvUrl(report.id)} download>Download the full report (.csv)</a></p>
      <div className="table-wrap">
        <table className="table stack bulk-report" aria-label="Import report">
          <thead>
            <tr><th>Row</th><th>Result</th><th>Company</th><th>Contact</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row_number}>
                <td data-label="Row">{r.row_number}</td>
                <td data-label="Result">{r.status === "error" ? "Error" : OUTCOME[r.status]}</td>
                <td data-label="Company"><CompanyCell company={r.company} /></td>
                <td data-label="Contact" style={{ overflowWrap: "anywhere" }}>{contactText(r.contact)}</td>
                <td data-label="Detail">{r.reason ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function History({ version }: { version: number }) {
  const [data, setData] = useState<Page<ImportSummary> | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<ImportSummary>(`${IMPORTS_URL}?limit=50`, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [version, retry]);

  return (
    <div className="action-card lead-import company-import">
      <h3>Past imports</h3>
      {failed ? (
        <p className="form-error" role="alert">Past imports could not be loaded. <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>Try again</button></p>
      ) : !data ? (
        <p className="muted" role="status">Loading…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No imports yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table stack bulk-report" aria-label="Past imports">
            <thead>
              <tr><th>When</th><th>File</th><th>Uploaded by</th><th>Rows</th><th>Result</th><th>Report</th></tr>
            </thead>
            <tbody>
              {data.items.map((b) => (
                <tr key={b.id}>
                  <td data-label="When"><LocalTime value={b.created_at} time /></td>
                  <td data-label="File" style={{ overflowWrap: "anywhere" }}>{b.file_name}</td>
                  <td data-label="Uploaded by">{b.uploaded_by.full_name}</td>
                  <td data-label="Rows">{b.total_rows}</td>
                  <td data-label="Result">{reportCounts(b)}</td>
                  <td data-label="Report"><a href={reportCsvUrl(b.id)} download>Report (.csv)</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// pob-006 (DEC-SCOPE-418 I8): 1 template, 2 file -> Check file (read only), 3 the preview -> Import, 4 the report. The Idempotency-Key belongs to the
// chosen file: a retry after a dropped connection replays the first result.
export default function RecruiterCompanyImport() {
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"" | "check" | "import">("");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const inFlight = useRef(false); // `busy` disables the buttons only after a re-render; a double click must not send twice
  const input = useRef<HTMLInputElement>(null);

  function choose(next: File | null) {
    setFile(next);
    setKey(newIdempotencyKey());
    setPreview(null);
    setError("");
  }

  function reset() {
    choose(null);
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
    const problem = precheck(file);
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
      <div className="action-card lead-import company-import">
        <h3>Import companies and contacts (CSV or Excel)</h3>
        <p className="muted">
          One row is a company and, optionally, one of its contacts; repeat the company on another row to add more people. A company name or contact that is already here is
          matched and the existing record is not changed. Nothing is saved until you check the file and press Import.
        </p>
        <form className="form" onSubmit={check} aria-busy={busy !== ""} noValidate>
          <h4>1. Download the template</h4>
          <a className="btn secondary" href={TEMPLATE_URL} download>Download the template (.csv)</a>
          <BulkColumnReference columns={IMPORT_COLUMNS} />
          <h4 style={{ marginTop: 16 }}>2. Choose the filled-in file</h4>
          <div className="field">
            <label htmlFor={FILE_ID}>Filled-in companies file</label>
            <input ref={input} id={FILE_ID} type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e: ChangeEvent<HTMLInputElement>) => choose(e.target.files?.[0] ?? null)} disabled={busy !== ""} aria-describedby={`${FILE_ID}-help`} />
            <p id={`${FILE_ID}-help`} className="muted field-help">
              CSV (UTF-8) or Excel (.xlsx), up to 1 MB and {IMPORT_MAX_ROWS.toLocaleString("en-IN")} rows.
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
            {fresh === 0 && <p className="form-warning">Nothing new to add — every row is already here or has an error.</p>}
            <PreviewTable preview={preview} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
              {fresh > 0 && (
                <button type="button" className="btn" onClick={commit} disabled={busy !== ""}>
                  {busy === "import" ? "Importing…" : `Import ${fresh.toLocaleString("en-IN")} new row${fresh === 1 ? "" : "s"}`}
                </button>
              )}
              <button type="button" className="btn secondary" onClick={reset} disabled={busy !== ""}>Choose another file</button>
            </div>
          </div>
        )}
        {report && <ImportResult report={report} />}
      </div>
      <History version={version} />
    </>
  );
}
