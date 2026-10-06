"use client";
import { type SyntheticEvent, useRef, useState } from "react";

import { isPage } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { FIELD_LABEL, type Mou, type MouEvent, mouHistoryUrl } from "@/lib/bdmMous";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";

const UNABLE = "Unable to load the MoU history.";

function title(e: MouEvent): string {
  if (e.kind === "created") return `Started at ${e.to_label}`;
  if (e.kind === "status") return `${e.from_label} → ${e.to_label}`;
  if (e.kind === "document") return "Document uploaded";
  if (e.kind === "renewed") return "Replaced by a renewal";
  const fields = e.changed.map((f) => FIELD_LABEL[f as keyof typeof FIELD_LABEL] ?? f).join(", ");
  return e.from_status !== e.to_status ? `Updated: ${fields} (${e.from_label} → ${e.to_label})` : `Updated: ${fields}`;
}

// bdm-005 (AC1; the BdmStageHistory look, .jtl): every recorded change, newest first, each with its actor and time. Loaded the first
// time the section is opened, so the card paints without it. Expired is derived, not a recorded change: it is shown as an automatic
// line, with no actor. Plain text only.
export default function BdmMouHistory({ mou }: { mou: Mou }) {
  const [items, setItems] = useState<MouEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const latest = useRef(0);

  async function load(offset: number) {
    const ticket = ++latest.current;
    setState("loading");
    const response = await fetch(mouHistoryUrl(mou.id, offset)).catch(() => null);
    const data: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    if (!isPage<MouEvent>(data)) return setState(offset === 0 ? "failed" : "ready");
    setTotal(data.total);
    setItems((current) => (offset === 0 ? data.items : appendUnique(current, data.items)));
    setState("ready");
  }
  const opened = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (event.currentTarget.open && state === "idle") void load(0);
  };

  return (
    <details onToggle={opened}>
      <summary>MoU history</summary>
      {state === "failed" ? (
        <p className="muted">
          {UNABLE}{" "}
          <button type="button" className="btn secondary small" onClick={() => void load(0)}>Try again</button>
        </p>
      ) : state === "idle" || (state === "loading" && items.length === 0) ? (
        <p className="muted" aria-live="polite">Loading…</p>
      ) : (
        <ol className="jtl" aria-label="MoU history" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {mou.expired_on && (
            <li className="jtl-row">
              <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" /></div>
              <div>
                <span className="jtl-date">{formatCalendarDate(mou.expired_on)}</span>
                <p className="jtl-title">Expired (automatic)</p>
                <p className="jtl-detail">The validity window ended on {formatCalendarDate(mou.valid_until)}.</p>
              </div>
            </li>
          )}
          {items.map((e) => (
            <li key={e.id} className="jtl-row">
              <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" /></div>
              <div>
                <span className="jtl-date">{formatSchoolDateTime(e.created_at, true)}</span>
                <p className="jtl-title">{title(e)}</p>
                <p className="jtl-detail">By {e.actor.full_name}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {state !== "failed" && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={state === "loading"}>
          {state === "loading" ? "Loading…" : "Show more"}
        </button>
      )}
    </details>
  );
}
