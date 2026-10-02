"use client";

import { useEffect, useState } from "react";
import { detailMessage, isPage } from "@/lib/apiErrors";
import { DOCUMENTS_URL, eventLabel, HistoryEvent, statusLabel } from "@/lib/agentDocuments";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

// AGN-009 (AC5): a document's history, oldest first, inline under its card (no dialog to trap focus in). Loaded when opened.
export default function AgentDocumentHistory({ id, name }: { id: string; name: string }) {
  const [events, setEvents] = useState<HistoryEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetch(`${DOCUMENTS_URL}/${id}/history?limit=200`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<HistoryEvent>(body)) return setError(detailMessage(body?.detail, "The history could not be loaded."));
        setEvents(body.items);
      })
      .catch(() => !controller.signal.aborted && setError("Network error. Check your connection and try again."));
    return () => controller.abort();
  }, [id, attempt]);

  const label = `History of ${name}`;
  if (error)
    return (
      <p className="form-error" role="alert">
        {error}{" "}
        <button type="button" className="btn secondary small" onClick={() => setAttempt((a) => a + 1)}>
          Retry
        </button>
      </p>
    );
  if (!events) return <p className="muted" aria-busy="true">Loading history…</p>;
  if (!events.length) return <p className="muted">No history recorded yet. Documents uploaded before history was kept start with their next action.</p>;
  return (
    <ol aria-label={label} style={{ margin: "12px 0 0", paddingLeft: 20 }}>
      {events.map((e) => (
        <li key={e.id} style={{ marginBottom: 6 }}>
          <strong>{eventLabel(e.event)}</strong>
          {e.to_status && e.event !== "uploaded" && e.event !== e.to_status && <span className="muted"> → {statusLabel(e.to_status)}</span>}
          <span className="muted">
            {" "}
            · {e.actor ?? "Unknown user"} · {formatDateTimeIn(e.created_at, viewerTimeZone())}
          </span>
          {e.notes && <div>{e.notes}</div>}
        </li>
      ))}
    </ol>
  );
}
