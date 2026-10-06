"use client";

import { useEffect, useState } from "react";

import type { Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import { getPage, teamLabel } from "@/lib/telecallerCatalogue";
import { IMPORTS_URL, importCounts, type ImportSummary } from "@/lib/telecallerImport";

// tel-006 (R11): the caller's last 50 imports (super_admin: everyone's), newest first; reloaded when `version` changes after an upload.
export default function TelecallerImportHistory({ version }: { version: number }) {
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
          <table className="table">
            <thead>
              <tr><th>When</th><th>Campaign</th><th>Team</th><th>Uploaded by</th><th>Rows</th><th>Result</th></tr>
            </thead>
            <tbody>
              {data.items.map((b) => (
                <tr key={b.id}>
                  <td data-label="When">{formatDate(b.created_at, true)}</td>
                  <td data-label="Campaign">{b.campaign.name}</td>
                  <td data-label="Team">{teamLabel(b.division)}</td>
                  <td data-label="Uploaded by">{b.uploaded_by.full_name}</td>
                  <td data-label="Rows">{b.total_rows}</td>
                  <td data-label="Result">{importCounts(b)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
