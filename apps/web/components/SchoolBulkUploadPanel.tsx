"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type RowReport = { row_number: number; status: string; error_message: string | null; created_student_id: string | null };
type BatchReport = { id: string; status: string; total_rows: number; accepted_count: number; rejected_count: number; rows: RowReport[] };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to process this upload.";
}

// SCH-002: download a template, fill it offline, upload it back -- a row that fails
// validation is named specifically (which row, which field, why) and never blocks the
// rows around it (SCH-002-AC04).
export default function SchoolBulkUploadPanel() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const fileInput = formElement.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) {
      setError("Choose a filled-in roster file first.");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/v1/school/students/bulk-upload", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body,
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(detailMessage(data.detail));
      return;
    }
    setReport(data);
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>1. Download the template</h2>
        <p className="muted">Fill it in offline, then upload it below. Columns: full name (required), date of birth, grade/class, an existing Teacher&apos;s email if you want to assign one, and a parent&apos;s name/email if you want one invited (or linked, if they already have an account).</p>
        <button type="button" className="btn secondary" onClick={() => window.open("/api/v1/school/students/roster-template", "_blank", "noreferrer")}>
          Download template (.csv)
        </button>
      </div>

      <div className="action-card">
        <h3>2. Upload your filled-in roster</h3>
        <form className="form" onSubmit={upload}>
          <div className="field">
            <label htmlFor="roster-file">Filled-in roster file</label>
            <input id="roster-file" name="file" type="file" accept=".csv" required />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Processing…" : "Upload roster"}</button>
        </form>
        {error && (
          <div className="form-error" role="alert" aria-live="assertive" style={{ marginTop: 8 }}>
            {error}
          </div>
        )}
      </div>

      {report && (
        <div className="card">
          <h2>Upload result</h2>
          <p>
            {report.accepted_count} of {report.total_rows} row{report.total_rows === 1 ? "" : "s"} accepted
            {report.rejected_count > 0 ? `, ${report.rejected_count} rejected` : ""}.
            Rows that succeeded are kept even though others failed.
          </p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Row</th><th>Result</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {report.rows.map((r) => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td>{r.status === "accepted" ? "Added" : "Rejected"}</td>
                    <td>{r.error_message || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
