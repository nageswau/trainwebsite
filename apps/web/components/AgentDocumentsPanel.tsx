"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import AgentDocumentCard from "./AgentDocumentCard";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentDocumentItem, DOCUMENTS_URL, VIEW_LABELS } from "@/lib/agentDocuments";
import type { User } from "@/lib/types";

const PAGE_SIZE = 20;
const EMPTY = {
  pending: "No documents are waiting for review.",
  uploaded: "No documents uploaded yet. Use Upload document to add the first one.",
};

// AGN-009 (G9): the Pending or Uploaded view (AGN-008's list pattern). Paging is local (a new view remounts this panel at page one);
// the previous page stays visible, dimmed, while the next loads; only the newest request may fill the list. A change made on a card
// reloads the page and is announced here, since the card may have left the view.
export default function AgentDocumentsPanel({ view, reloadKey, user }: { view: "pending" | "uploaded"; reloadKey: number; user: User }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<AgentDocumentItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ view, limit: String(PAGE_SIZE), offset: String(offset) });
    fetch(`${DOCUMENTS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentDocumentItem>(body)) return setLoadError(detailMessage(body?.detail, "The documents could not be loaded."));
        if (!body.items.length && offset > 0) return setOffset(Math.max(0, offset - PAGE_SIZE)); // the last card on this page left the view
        setData(body);
      })
      .catch(() => !controller.signal.aborted && setLoadError("Network error. Check your connection and try again."))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [view, offset, reloadKey, attempt]);

  function changed(text?: string) {
    setMessage(text ?? null);
    setAttempt((a) => a + 1);
  }

  return (
    <section className="action-card" aria-labelledby="agent-documents-heading" style={{ gridColumn: "1 / -1" }}>
      <h3 id="agent-documents-heading">{VIEW_LABELS[view]}</h3>
      <p className="form-message" role="status" hidden={!message}>
        {message}
      </p>
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
          Loading documents…
        </p>
      )}
      {data && !data.items.length && !loading && (
        <p className="muted">
          {EMPTY[view]}{" "}
          {view === "pending" && <Link href="/overseas/agent/documents?view=uploaded">Show all uploaded documents</Link>}
        </p>
      )}
      {data && data.items.length > 0 && (
        <ul aria-label={VIEW_LABELS[view]} aria-busy={loading} className="card-stack" style={{ listStyle: "none", padding: 0, opacity: loading ? 0.6 : 1 }}>
          {data.items.map((doc) => (
            <AgentDocumentCard key={doc.id} doc={doc} user={user} onChanged={changed} />
          ))}
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
