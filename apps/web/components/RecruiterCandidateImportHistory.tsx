"use client";

import { useEffect, useState } from "react";

import LocalTime from "@/components/LocalTime";
import type { Page } from "@/lib/apiErrors";
import { IMPORTS_URL, reportCounts, reportCsvUrl, type ImportSummary } from "@/lib/recruiterCandidateImport";
import { getPage } from "@/lib/telecallerCatalogue";

// hrc-013 (DEC-SCOPE-391 I11): the last 50 imports -- the caller's own, everyone's for a placement manager or super_admin -- newest first;
// reloaded when `version` changes after an import.
export default function RecruiterCandidateImportHistory({ version }: { version: number }) {
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
    <div className="action-card lead-import">
      <h3>Past imports</h3>
      {failed ? (
        <p className="form-error" role="alert">Past imports could not be loaded. <button type="button" className="btn secondary" onClick={() => setRetry((n) => n + 1)}>Retry</button></p>
      ) : !data ? (
        <p className="muted" role="status">Loading…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No imports yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table stack bulk-report" aria-label="Past imports">
            <thead>
              <tr><th>When</th><th>File</th><th>Source</th><th>Uploaded by</th><th>Rows</th><th>Result</th><th>Report</th></tr>
            </thead>
            <tbody>
              {data.items.map((b) => (
                <tr key={b.id}>
                  <td data-label="When"><LocalTime value={b.created_at} time /></td>
                  <td data-label="File" style={{ overflowWrap: "anywhere" }}>{b.file_name}</td>
                  <td data-label="Source">{b.source.name}</td>
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
