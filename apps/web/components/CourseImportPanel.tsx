"use client";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type FormEvent, useRef, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { courseImportUrl, courseTemplateUrl } from "@/lib/courseMaster";
import { newIdempotencyKey } from "@/lib/idempotencyKey";

// upc-017 (CO14, Q-21): a university's course CSV -- download the template, upload; each row is added, a duplicate (same title + level)
// or invalid with its reason. The Idempotency-Key belongs to the chosen file: a retry after a dropped connection replays the first
// result instead of importing twice (upc-005's flow, without the history).
const MAX_BYTES = 1024 * 1024;
const RESULT = { duplicate: "Duplicate", invalid: "Invalid" } as Record<string, string>;
type Row = { row_number: number; status: string; title: string; level: string; reason: string | null };
type Report = { created_count: number; duplicate_count: number; invalid_count: number; rows: Row[] };

export default function CourseImportPanel({ universityId }: { universityId: string }) {
  const router = useRouter();
  const [chosen, setChosen] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not upload twice
  const input = useRef<HTMLInputElement>(null);
  const fileId = `course-import-${universityId}`;

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setChosen(file ? { file, key: newIdempotencyKey() } : null);
    setError(null);
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const file = chosen?.file;
    const problem = !file ? "Choose a filled-in CSV file first." : !file.name.toLowerCase().endsWith(".csv") ? "Choose a .csv file." : file.size > MAX_BYTES ? "The file is larger than 1 MB." : null;
    if (problem || !chosen) return setError(problem);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", chosen.file);
    const outcome = await sendRequest(courseImportUrl(universityId), { method: "POST", headers: { "Idempotency-Key": chosen.key }, body });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setReport(outcome.data as Report);
    setChosen(null);
    if (input.current) input.current.value = "";
    router.refresh();
  }

  const skipped = report?.rows.filter((r) => r.status !== "created") ?? [];
  return (
    <form onSubmit={upload} noValidate aria-label="Import courses" aria-busy={busy} className="card" style={{ padding: 14, display: "grid", gap: 10 }}>
      <p className="muted" style={{ margin: 0 }}>
        One course per row: title, level (UG, PG, PhD, Diploma, Foundation), category and duration are required; intakes are months separated by
        &quot;;&quot; (Sep;Jan). Commission and scholarships are set on each course. Up to 1,000 rows, 1 MB.
      </p>
      <p style={{ margin: 0 }}><a className="btn ghost small" href={courseTemplateUrl(universityId)} download>Download the template</a></p>
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor={fileId}>CSV file</label>
        <input id={fileId} ref={input} type="file" accept=".csv,text/csv" onChange={choose} disabled={busy} />
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions"><button type="submit" className="btn small" disabled={busy}>{busy ? "Importing…" : "Import"}</button></div>
      {report && (
        <div role="status" style={{ display: "grid", gap: 8 }}>
          <p style={{ margin: 0 }}>{`${report.created_count} added, ${report.duplicate_count} duplicate, ${report.invalid_count} invalid.`}</p>
          {skipped.length > 0 && (
            <div className="table-wrap">
              <table className="table bulk-report" aria-label="Rows not added">
                <thead><tr><th>Row</th><th>Title</th><th>Result</th><th>Detail</th></tr></thead>
                <tbody>
                  {skipped.map((r) => (
                    <tr key={r.row_number}>
                      <td data-label="Row">{r.row_number}</td>
                      <td data-label="Title">{r.title || "-"}</td>
                      <td data-label="Result">{RESULT[r.status] ?? r.status}</td>
                      <td data-label="Detail">{r.reason ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </form>
  );
}
