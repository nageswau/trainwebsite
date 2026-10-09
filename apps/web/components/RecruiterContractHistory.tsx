"use client";
import { type SyntheticEvent, useRef, useState } from "react";

import { isPage } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { type Contract, type ContractEvent, contractHistoryUrl, FIELD_LABEL } from "@/lib/recruiterContracts";

const UNABLE = "Unable to load the contract history.";

function title(e: ContractEvent): string {
  if (e.kind === "created") return `Started at ${e.to_label}`;
  if (e.kind === "status") return `${e.from_label} → ${e.to_label}`;
  if (e.kind === "document") return `${e.changed.map((f) => FIELD_LABEL[f] ?? f).join(", ")} uploaded`;
  if (e.kind === "renewed") return "Replaced by a renewal";
  const fields = e.changed.map((f) => FIELD_LABEL[f] ?? f).join(", ");
  return e.from_status !== e.to_status ? `Updated: ${fields} (${e.from_label} → ${e.to_label})` : `Updated: ${fields}`;
}

// rec-030 (the BdmMouHistory look, .jtl): every recorded change, newest first, each with its actor and time. Loaded the first time the
// section is opened. Expired is derived, not a recorded change: it is shown as an automatic line with no actor. Plain text only.
export default function RecruiterContractHistory({ contract }: { contract: Contract }) {
  const [items, setItems] = useState<ContractEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const latest = useRef(0);

  async function load(offset: number) {
    const ticket = ++latest.current;
    setState("loading");
    const response = await fetch(contractHistoryUrl(contract.id, offset)).catch(() => null);
    const data: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    if (!isPage<ContractEvent>(data)) return setState(offset === 0 ? "failed" : "ready");
    setTotal(data.total);
    setItems((current) => (offset === 0 ? data.items : appendUnique(current, data.items)));
    setState("ready");
  }
  const opened = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (event.currentTarget.open && state === "idle") void load(0);
  };

  return (
    <details onToggle={opened}>
      <summary>Contract history</summary>
      {state === "failed" ? (
        <p className="muted">
          {UNABLE}{" "}
          <button type="button" className="btn secondary small" onClick={() => void load(0)}>Try again</button>
        </p>
      ) : state === "idle" || (state === "loading" && items.length === 0) ? (
        <p className="muted" aria-live="polite">Loading…</p>
      ) : (
        <ol className="jtl" aria-label="Contract history" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {contract.expired_on && (
            <li className="jtl-row">
              <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" /></div>
              <div>
                <span className="jtl-date">{formatCalendarDate(contract.expired_on)}</span>
                <p className="jtl-title">Expired (automatic)</p>
                <p className="jtl-detail">The contract ended on {formatCalendarDate(contract.end_date)}.</p>
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
