"use client";

import { useEffect, useState } from "react";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { documentName, DocumentRequestItem, formatDateTime, REQUESTS_URL, VIEW_LABELS } from "@/lib/agentDocuments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const PAGE_SIZE = 20;

// AGN-009 (G4/G5, AC4): the "Additional documents" view -- open requests, until an upload made against one fulfils it or a member
// cancels it. Fulfilling happens in Upload document (pick the request there).
export default function AgentDocumentRequestsPanel({ reloadKey }: { reloadKey: number }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<DocumentRequestItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; failed: boolean } | null>(null);
  const focusAfter = useFocusAfterRender();

  useEffect(() => {
    const controller = new AbortController(); // aborted by the cleanup when the view, page or reload key changes
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ status: "open", limit: String(PAGE_SIZE), offset: String(offset) });
    fetch(`${REQUESTS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<DocumentRequestItem>(body)) return setLoadError(detailMessage(body?.detail, "The requests could not be loaded."));
        if (!body.items.length && offset > 0) return setOffset(Math.max(0, offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => !controller.signal.aborted && setLoadError("Network error. Check your connection and try again."))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [offset, reloadKey, attempt]);

  async function cancel(item: DocumentRequestItem, label: string) {
    setCancelling(item.id);
    setNote(null);
    let failed: string | null = null;
    let reload = true;
    try {
      const response = await fetch(`${REQUESTS_URL}/${item.id}/cancel`, { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        failed = detailMessage(body?.detail, "The request could not be cancelled.");
        reload = response.status === 409; // someone else fulfilled or cancelled it first
      }
    } catch {
      failed = "Couldn't reach the server. Check your connection and try again.";
      reload = false;
    }
    setCancelling(null);
    setNote({ text: failed ?? `Request for ${label} cancelled.`, failed: failed !== null });
    focusAfter("agent-requests-note");
    if (reload) setAttempt((a) => a + 1);
  }

  return (
    <section className="action-card" aria-labelledby="agent-requests-heading" style={{ gridColumn: "1 / -1" }}>
      <h3 id="agent-requests-heading">{VIEW_LABELS.additional}</h3>
      {note && (
        <p id="agent-requests-note" tabIndex={-1} className={note.failed ? "form-error" : "form-message"} role={note.failed ? "alert" : "status"}>
          {note.text}
        </p>
      )}
      {loadError && (
        <p className="form-error" role="alert">
          {loadError}{" "}
          <button type="button" className="btn secondary small" onClick={() => setAttempt((a) => a + 1)}>
            Retry
          </button>
        </p>
      )}
      {!data && loading && !loadError && (
        <p className="muted" aria-busy="true">
          Loading requests…
        </p>
      )}
      {data && !data.items.length && !loading && <p className="muted">No open requests. Requests you make appear here until a document is uploaded against them.</p>}
      {data && data.items.length > 0 && (
        <ul aria-label="Open requests" aria-busy={loading} className="card-stack" style={{ listStyle: "none", padding: 0, opacity: loading ? 0.6 : 1 }}>
          {data.items.map((r) => {
            const label = `${documentName(r)} from ${r.student}`;
            return (
              <li key={r.id} className="card" style={{ padding: 16 }}>
                <strong>{r.student}</strong> — {documentName(r)} <span className="status pending">Open</span>
                {r.note && <div>{r.note}</div>}
                <div className="muted">
                  Requested{r.requested_by ? ` by ${r.requested_by}` : ""} · {formatDateTime(r.created_at)}
                </div>
                <div className="actions" style={{ marginTop: 8 }}>
                  <button type="button" className="btn secondary small" aria-label={`Cancel request for ${label}`} disabled={cancelling === r.id} onClick={() => cancel(r, label)}>
                    {cancelling === r.id ? "Cancelling…" : "Cancel request"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {data && data.total > PAGE_SIZE && (
        <div className="actions" style={{ marginTop: 12, alignItems: "center" }}>
          <span className="muted">
            Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
          </span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </button>
        </div>
      )}
    </section>
  );
}
