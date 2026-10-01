"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BulkColumnReference from "@/components/BulkColumnReference";
import { SCHOOL_ONBOARDING } from "@/lib/bulkEntry";
import { newIdempotencyKey } from "@/lib/idempotencyKey";
import { type Feedback, errorText, toneClass } from "@/lib/welcomeLink";

type RowReport = {
  row_number: number;
  status: "accepted" | "rejected";
  error_message: string | null;
  school_code: string | null;
  school_name: string | null;
  coordinator_email: string | null;
  email_status: string | null;
};
type BatchReport = { total_rows: number; accepted_count: number; rejected_count: number; rows: RowReport[] };

const MAX_BYTES = 1024 * 1024;
const NETWORK_ERROR = "The connection dropped. Upload again — the same file won't be added twice.";
const BUSY_MESSAGE = "Uploading — creating schools and sending set-password emails. Large files can take up to a minute.";
const UNDELIVERED = new Set(["not_configured", "failed"]);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const undelivered = (row: RowReport) => row.status === "accepted" && row.email_status !== null && UNDELIVERED.has(row.email_status);

function precheck(file: File | undefined): string | null {
  if (!file) return "Choose a filled-in CSV file first.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size > MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function rowDetail(row: RowReport): string {
  if (row.status === "rejected") return row.error_message ?? "Rejected";
  if (row.email_status === "sent") return "Set-password link emailed";
  if (undelivered(row)) return "Email not delivered — re-send from the Users page";
  return "Check the Users page for set-password status"; // a replayed report: delivery happened on the first upload
}

function summary(report: BatchReport): Feedback {
  if (report.accepted_count === 0) return { text: "No schools were onboarded. Fix the rows below and upload again.", tone: "error" };
  const missed = report.rows.filter(undelivered).length;
  const emails = missed ? ` ${plural(missed, "welcome email")} ${missed === 1 ? "was" : "were"} not delivered — re-send from the Users page.` : "";
  if (report.rejected_count === 0) return { text: `${plural(report.accepted_count, "school")} onboarded.${emails}`, tone: "success" };
  return {
    text: `${report.accepted_count} of ${plural(report.total_rows, "school")} onboarded, ${report.rejected_count} rejected. Schools that succeeded are kept — fix the rejected rows and upload just those.${emails}`,
    tone: "warning",
  };
}

function OnboardReport({ report }: { report: BatchReport }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [report]);
  const note = summary(report);
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Upload result</h4>
      <p className={toneClass[note.tone]}>{note.text}</p>
      <div className="table-wrap">
        <table className="table bulk-report">
          <thead>
            <tr><th>Row</th><th>Result</th><th>School ID</th><th>School</th><th>Coordinator</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row_number}>
                <td data-label="Row">{r.row_number}</td>
                <td data-label="Result">{r.status === "accepted" ? "Added" : "Rejected"}</td>
                <td data-label="School ID">{r.school_code ?? "-"}</td>
                <td data-label="School">{r.school_name ?? "-"}</td>
                <td data-label="Coordinator">{r.coordinator_email ?? "-"}</td>
                <td data-label="Detail">{rowDetail(r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ENH-029: download the header-only template, fill one school per row, upload it. Each row succeeds or fails on its own. The
// Idempotency-Key belongs to the chosen file: a retry of that file after a dropped connection replays the first result instead
// of creating the schools twice; choosing a file again is a new upload.
export default function AdminSchoolBulkOnboardPanel() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);
  const target = SCHOOL_ONBOARDING;
  const fileId = `${target.id}-file`;

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setChosen(file ? { file, key: newIdempotencyKey() } : null);
    setError(null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = precheck(chosen?.file);
    if (problem || !chosen) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", chosen.file);
    try {
      const response = await fetch(target.uploadUrl, { method: "POST", headers: { "Idempotency-Key": chosen.key }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(errorText(data.detail, "Unable to process this upload."));
        return;
      }
      setReport(data);
      setChosen(null);
      if (input.current) input.current.value = "";
      router.refresh();
    } catch {
      setError(NETWORK_ERROR);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card bulk-onboarding">
      <h3>{target.title}</h3>
      <p className="muted">Add many partner schools at once. Each school gets its own coordinator account and set-password email, exactly like Create school.</p>
      <h4>1. Download the template</h4>
      <a className="btn secondary" href={target.templateUrl} download>Download the template (.csv)</a>
      <BulkColumnReference columns={target.columns} />
      <h4 style={{ marginTop: 16 }}>2. Upload the filled-in file</h4>
      <form className="form" onSubmit={upload} aria-busy={busy} noValidate>
        <div className="field">
          <label htmlFor={fileId}>Filled-in schools file</label>
          <input ref={input} id={fileId} type="file" accept=".csv,text/csv" onChange={choose} disabled={busy} aria-describedby={`${fileId}-help`} />
          <p id={`${fileId}-help`} className="muted field-help">CSV, up to 1 MB and 100 schools. One school per row.</p>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Uploading…" : "Upload schools"}</button>
      </form>
      <p className="visually-hidden" role="status" aria-live="polite">{busy ? BUSY_MESSAGE : ""}</p>
      {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
      {report && <OnboardReport report={report} />}
    </div>
  );
}
