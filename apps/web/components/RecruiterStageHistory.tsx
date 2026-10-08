"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { changedBy, historyUrl, type StageEvent } from "@/lib/recruiterPipeline";

const UNABLE = "Unable to load the stage history.";

function title(e: StageEvent): string {
  if (e.event === "lost") return `Marked lost at ${e.to_label}`;
  if (e.event === "reopen") return `Reopened at ${e.to_label}`;
  return `${e.from_label} → ${e.to_label}`;
}

// rec-005 (AC1): every stage change, Lost and reopen, newest first (BdmStageHistory's look and loading rules). `version` changes after each
// write on the page, which reloads the first page; only the newest request may update the list. Plain text only.
export default function RecruiterStageHistory({ companyId, initial, version }: { companyId: string; initial: Page<StageEvent> | null; version: number }) {
  const [items, setItems] = useState<StageEvent[]>(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [failed, setFailed] = useState(initial === null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (offset: number) => {
    const ticket = ++latest.current;
    setLoading(true);
    const response = await fetch(historyUrl(companyId, offset)).catch(() => null);
    const data: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    setLoading(false);
    if (!isPage<StageEvent>(data)) {
      if (offset === 0) setFailed(true);
      return;
    }
    setFailed(false);
    setTotal(data.total);
    setItems((current) => (offset === 0 ? data.items : appendUnique(current, data.items)));
  }, [companyId]);

  useEffect(() => {
    if (version > 0) void load(0);
  }, [version, load]);

  return (
    <section className="action-card wide" aria-label="Stage history">
      <h3>Stage history</h3>
      {failed ? (
        <p className="muted">
          {UNABLE}{" "}
          <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>
            Try again
          </button>
        </p>
      ) : items.length === 0 ? (
        <p className="muted">No stage changes yet.</p>
      ) : (
        <ol className="jtl" aria-label="Stage history" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((e) => (
            <li key={e.id} className="jtl-row">
              <div className="jtl-rail" aria-hidden="true">
                <span className="jtl-node" />
              </div>
              <div>
                <span className="jtl-date">{formatSchoolDateTime(e.created_at, true)}</span>
                <p className="jtl-title">{title(e)}</p>
                <p className="jtl-detail">{changedBy(e)}</p>
                {e.reason && <p className="jtl-detail" style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{e.event === "manual" ? "Note" : "Reason"}: {e.reason}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {!failed && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={loading}>
          {loading ? "Loading…" : "Show more"}
        </button>
      )}
    </section>
  );
}
