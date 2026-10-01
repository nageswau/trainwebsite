"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BulkColumnReference from "@/components/BulkColumnReference";
import type { BulkTarget } from "@/lib/bulkEntry";
import { newIdempotencyKey } from "@/lib/idempotencyKey";

type RowReport = { row_number: number; status: string; error_message: string | null; student_code: string | null; created_record_id: string | null };
type BatchReport = { id: string; total_rows: number; accepted_count: number; rejected_count: number; rows: RowReport[] };

const NETWORK_ERROR = "The connection dropped. Upload again — the same file won't be added twice.";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to process this upload.";
}

// ENH-028: download a template pre-filled with the portfolio's students, fill the marks/results offline, upload it back. Each
// row succeeds or fails on its own. The Idempotency-Key belongs to the chosen file: a retry of that file after a dropped
// connection sends the same key, so the server replays the first result instead of adding the rows again.
export default function SchoolBulkEntryPanel({ target, hasStudents }: { target: BulkTarget; hasStudents: boolean }) {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const [file, setFile] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);

  useEffect(() => {
    if (report) resultHeading.current?.focus();
  }, [report]);

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    setFile(chosen ? { file: chosen, key: newIdempotencyKey() } : null);
    setError(null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a filled-in CSV file first.");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", file.file);
    try {
      const response = await fetch(target.uploadUrl, { method: "POST", headers: { "Idempotency-Key": file.key }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(detailMessage(data.detail));
        return;
      }
      setReport(data);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      router.refresh();
    } catch {
      setError(NETWORK_ERROR);
    } finally {
      setBusy(false);
    }
  }

  const fileId = `${target.id}-file`;
  return (
    <div className="portal-content">
      <details className="card">
        <summary><strong>{target.title}</strong></summary>
        {!hasStudents ? (
          <p className="muted" style={{ marginTop: 12 }}>No students in your portfolio yet. Bulk entry becomes available once a school is assigned to you.</p>
        ) : (
          <div className="card-stack" style={{ marginTop: 12 }}>
            <div>
              <h3>1. Download the template</h3>
              <p className="muted">One row per student in your portfolio. Fill in only the students you are entering; rows you leave blank are skipped.</p>
              <a className="btn secondary" href={target.templateUrl} download>Download the pre-filled template (.csv)</a>
              <BulkColumnReference columns={target.columns} />
            </div>

            <div className="action-card">
              <h3>2. Upload the filled-in file</h3>
              <form className="form" onSubmit={upload} aria-busy={busy} noValidate>
                <div className="field">
                  <label htmlFor={fileId}>Filled-in {target.noun} file</label>
                  <input ref={fileInput} id={fileId} type="file" accept=".csv,text/csv" onChange={choose} disabled={busy} aria-describedby={`${fileId}-help`} />
                  <p id={`${fileId}-help`} className="muted field-help">CSV, up to 1 MB and 500 filled-in rows.</p>
                </div>
                <button className="btn" disabled={busy}>{busy ? "Uploading…" : `Upload ${target.noun}`}</button>
              </form>
              <p className="visually-hidden" role="status" aria-live="polite">{busy ? "Uploading…" : ""}</p>
              {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
            </div>

            {report && (
              <div>
                <h3 ref={resultHeading} tabIndex={-1}>Upload result</h3>
                <p>
                  {report.accepted_count} of {report.total_rows} row{report.total_rows === 1 ? "" : "s"} added
                  {report.rejected_count > 0 ? `, ${report.rejected_count} rejected` : ""}. Rows that succeeded are kept.
                </p>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr><th>Row</th><th>Student ID</th><th>Result</th><th>Detail</th></tr>
                    </thead>
                    <tbody>
                      {report.rows.map((r) => (
                        <tr key={r.row_number}>
                          <td data-label="Row">{r.row_number}</td>
                          <td data-label="Student ID">{r.student_code ?? "-"}</td>
                          <td data-label="Result">{r.status === "accepted" ? "Added" : "Rejected"}</td>
                          <td data-label="Detail">{r.error_message ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </details>
    </div>
  );
}
