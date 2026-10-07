"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import type { Page } from "@/lib/apiErrors";
import { TIMELINE_LIMIT, actorName, timelineEntry, type TimelineRow } from "@/lib/leadTimeline";
import { getPage } from "@/lib/telecallerCatalogue";

type State = { rows: TimelineRow[]; total: number } | "loading" | "failed";

const pageOf = (page: Page<TimelineRow>): State => ({ rows: page.items, total: page.total });
// A follow-up has up to three entries with its id (scheduled / done / cancelled): the event keeps their keys apart.
const keyOf = (row: TimelineRow) => `${row.kind}-${row.event ?? ""}-${row.id}`;

/** tel-015 (DEC-SCOPE-114 D8): a lead's merged timeline, newest first, as the `.jtl` timeline -- shared by the telecaller / manager
 *  detail, the counselor's lead and the admin History. `initial` is the server-rendered first page (`null`: it failed; omitted: load
 *  here). A `version` change re-reads the first page (something on the page just changed); "Show older entries" appends the next one. */
export default function LeadTimeline({ url, initial, version, label = "Lead activity" }: {
  url: string; initial?: Page<TimelineRow> | null; version: number; label?: string;
}) {
  const [state, setState] = useState<State>(initial === undefined ? "loading" : initial === null ? "failed" : pageOf(initial));
  const [older, setOlder] = useState<"idle" | "loading" | "failed">("idle");
  const latest = useRef(0);
  const firstVersion = useRef(initial === undefined ? null : version);

  const load = useCallback(() => {
    const request = ++latest.current;
    setOlder("idle");
    getPage<TimelineRow>(`${url}?limit=${TIMELINE_LIMIT}&offset=0`).then(
      (page) => request === latest.current && setState(pageOf(page)),
      () => request === latest.current && setState("failed"),
    );
  }, [url]);

  useEffect(() => {
    if (firstVersion.current === version) return; // the server's first page is already current
    firstVersion.current = null;
    load();
  }, [load, version]);

  function retry() {
    setState("loading");
    load();
  }

  function showOlder() {
    if (typeof state !== "object") return;
    const request = latest.current;
    setOlder("loading");
    getPage<TimelineRow>(`${url}?limit=${TIMELINE_LIMIT}&offset=${state.rows.length}`).then(
      (page) => {
        if (request !== latest.current) return; // a refresh replaced the list meanwhile
        setState((current) => {
          if (typeof current !== "object") return current;
          const seen = new Set(current.rows.map(keyOf));
          return { rows: [...current.rows, ...page.items.filter((r) => !seen.has(keyOf(r)))], total: page.total };
        });
        setOlder("idle");
      },
      () => setOlder("failed"),
    );
  }

  if (state === "loading") return <p className="muted" role="status" style={{ fontSize: 13 }}>Loading the activity…</p>;
  if (state === "failed") {
    return (
      <p className="form-error" role="alert" style={{ fontSize: 13, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        Unable to load the activity.
        <button type="button" className="btn secondary small" onClick={retry}>Retry</button>
      </p>
    );
  }
  if (state.rows.length === 0) return <p className="muted" style={{ fontSize: 13 }}>No activity yet.</p>;

  return (
    <>
      <ol className="jtl" aria-label={label} style={{ listStyle: "none", margin: "8px 0 0", padding: 0 }}>
        {state.rows.map((row) => {
          const entry = timelineEntry(row);
          const tone = { "--jtl-color": entry.tone } as React.CSSProperties;
          return (
            <li className="jtl-row" key={keyOf(row)}>
              <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" style={tone} /></div>
              <div style={{ minWidth: 0 }}>
                <p className="jtl-title" style={{ fontSize: 14, overflowWrap: "anywhere" }}>
                  {entry.title}
                  <span className="jtl-badge" style={tone}>{entry.badge}</span>
                </p>
                <p className="jtl-detail">{actorName(row)} · <LocalTime value={row.at} time /></p>
                {(entry.meta.length > 0 || entry.when) && (
                  <p className="jtl-detail" style={{ overflowWrap: "anywhere" }}>
                    {entry.meta.join(" · ")}
                    {entry.when && <>{entry.meta.length > 0 && " · "}{entry.when.label} <LocalTime value={entry.when.value} time /></>}
                  </p>
                )}
                {entry.detail && (
                  <p className="jtl-detail" style={{ color: "var(--ink)", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{entry.detail}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {state.total > state.rows.length && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 8 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {state.rows.length} of {state.total} entries.</span>
          <button type="button" className="btn secondary small" disabled={older === "loading"} onClick={showOlder}>
            {older === "loading" ? "Loading…" : "Show older entries"}
          </button>
        </div>
      )}
      {older === "failed" && <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load older entries.</p>}
    </>
  );
}
