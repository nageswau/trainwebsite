"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import AgentApplicationDetail from "./AgentApplicationDetail";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentApplicationDetail as Detail, AgentApplicationItem, APPLICATIONS_URL, deadlineText, GROUP_LABELS, StatusGroup, stageLabel, todayIso } from "@/lib/agentApplications";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const PAGE_SIZE = 20;
const LOAD_FAILED = "The applications could not be loaded.";

// AGN-008: the agency's applications for one sidebar filter. Paging is local (a new filter remounts this panel at page one); the
// previous page stays visible, dimmed, while the next loads; only the newest request may fill the list.
export default function AgentApplicationsPanel({ group, reloadKey, isMaster = false }: { group: StatusGroup; reloadKey: number; isMaster?: boolean }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<AgentApplicationItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const focusAfter = useFocusAfterRender();

  useEffect(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ status: group, limit: String(PAGE_SIZE), offset: String(offset) });
    fetch(`${APPLICATIONS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentApplicationItem>(body)) return setLoadError(detailMessage(body?.detail, LOAD_FAILED));
        setData(body);
      })
      .catch(() => !controller.signal.aborted && setLoadError("Network error. Check your connection and try again."))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [group, offset, reloadKey, attempt]);

  function replace(next: Detail) {
    setData((current) => current && { ...current, items: current.items.map((a) => (a.id === next.id ? { ...a, ...next } : a)) });
  }
  function close(id: string) {
    focusAfter(`view-${id}`); // focus returns to the card's View button once the detail has closed
    setOpenId(null);
  }

  const today = todayIso();
  return (
    <section className="action-card" aria-labelledby="agent-applications-heading" style={{ gridColumn: "1 / -1" }}>
      <h3 id="agent-applications-heading">{GROUP_LABELS[group]}</h3>
      {loadError && (
        <p className="form-error" role="alert">
          {loadError}{" "}
          <button type="button" className="btn secondary small" onClick={() => setAttempt((a) => a + 1)}>
            Retry
          </button>
        </p>
      )}
      {!data && loading && !loadError && <p className="muted" aria-busy="true">Loading applications…</p>}
      {data && !data.items.length && !loading &&
        (group === "all" ? (
          <p className="muted">No applications yet. Use Create application to add the first one.</p>
        ) : (
          <p className="muted">
            No applications match this filter. <Link href="/overseas/agent/applications">Show all applications</Link>
          </p>
        ))}
      {data && data.items.length > 0 && (
        <ul aria-label="Applications" aria-busy={loading} className="card-stack" style={{ listStyle: "none", padding: 0, opacity: loading ? 0.6 : 1 }}>
          {data.items.map((a) => {
            const title = `${a.student} — ${a.university}`;
            const deadline = deadlineText(a.nearest_deadline, today);
            return (
              <li key={a.id} className="card" style={{ padding: 16 }}>
                <strong>{a.student}</strong> — {a.university}
                {!a.has_login && <span className="badge" style={{ marginLeft: 8 }}>no login</span>}
                <div>
                  <span className={a.status === "withdrawn" ? "status error" : "badge"}>{stageLabel(a.status)}</span>
                  {a.application_reference && <span className="muted"> · ID {a.application_reference}</span>}
                  {a.course && <span className="muted"> · {a.course}</span>}
                  <span className="muted"> · {a.intake}</span>
                </div>
                {deadline && <div className="muted">{deadline}</div>}
                {a.next_action && <div className="muted">Next: {a.next_action}</div>}
                <button
                  type="button"
                  id={`view-${a.id}`}
                  className="btn secondary small"
                  aria-expanded={openId === a.id}
                  aria-label={`View ${title}`}
                  onClick={() => (openId === a.id ? close(a.id) : setOpenId(a.id))}
                  style={{ marginTop: 8 }}
                >
                  {openId === a.id ? "Hide" : "View"}
                </button>
                {openId === a.id && <AgentApplicationDetail id={a.id} isMaster={isMaster} onChanged={replace} onClose={() => close(a.id)} />}
              </li>
            );
          })}
        </ul>
      )}
      {data && data.total > 0 && (
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
