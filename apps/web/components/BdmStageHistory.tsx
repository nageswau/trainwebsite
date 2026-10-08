"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { HISTORY_PAGE, historyUrl, type StageEvent } from "@/lib/bdmPipeline";
import { formatSchoolDateTime } from "@/lib/formatDate";

const UNABLE = "Unable to load the stage history.";

function title(e: StageEvent): string {
  if (e.kind === "lost") return `Marked lost at ${e.to_label}`;
  if (e.kind === "revived") return `Revived at ${e.to_label}`;
  if (e.kind === "reopened") return `Reopened at ${e.to_label}`;
  return `${e.from_label} → ${e.to_label}`;
}

// bdm-004 (spec §8.2, AC2): every move, Lost and Revive, newest first; the bdm-006 history look (.jtl). `version` changes after each
// write on this page, which reloads the first page; only the newest request may update the list. Plain text only. upc-007 reuses it for a
// university's history (`url`: its stage-history endpoint, a string so a server page can pass it; and the "reopened" kind).
export default function BdmStageHistory({ orgId, initial, version, url }: {
  orgId: string; initial: Page<StageEvent> | null; version: number; url?: string;
}) {
  const [items, setItems] = useState<StageEvent[]>(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [failed, setFailed] = useState(initial === null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (offset: number) => {
    const ticket = ++latest.current;
    setLoading(true);
    const response = await fetch(url ? `${url}?limit=${HISTORY_PAGE}&offset=${offset}` : historyUrl(orgId, offset)).catch(() => null);
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
  }, [orgId, url]);

  useEffect(() => {
    if (version > 0) void load(0); // reload only when a write on this page bumps the version
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
                <p className="jtl-detail">By {e.actor.full_name}</p>
                {e.note && <p className="jtl-detail" style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{e.kind === "move" ? "Note" : "Reason"}: {e.note}</p>}
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
