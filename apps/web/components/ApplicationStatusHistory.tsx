"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { stageLabel, type HistoryEntry } from "@/lib/agentApplications";
import { isTerminal } from "@/lib/applicationOutcome";
import { subStatusLabel } from "@/lib/applicationSubStatus";

const UNABLE = "Unable to load the status history.";

// ccrm-016 (DEC-SCOPE-247): one overseas application's status history, oldest first -- stage, sub-status, the outcome a row set, author,
// time, then its note (or its reason when it has no note). A student's rows arrive without author, notes or reason (H2: filtered on the
// server). Plain text only.
export default function ApplicationStatusHistory({ applicationId }: { applicationId: string }) {
  const [rows, setRows] = useState<HistoryEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const ticket = ++latest.current;
    setFailed(false);
    setRows(null);
    const response = await fetch(`/api/v1/workflows/overseas/applications/${applicationId}/status`).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    if (!Array.isArray(data?.history)) setFailed(true);
    else setRows(data.history);
  }, [applicationId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed)
    return (
      <p className="muted" style={{ marginTop: 8 }}>
        {UNABLE}{" "}
        <button type="button" className="btn secondary small" onClick={() => void load()}>
          Try again
        </button>
      </p>
    );
  if (rows === null) return <p className="muted" style={{ marginTop: 8 }}>Loading status history…</p>;
  if (rows.length === 0) return <p className="muted" style={{ marginTop: 8 }}>No status changes recorded yet.</p>;
  return (
    <ol aria-label="Status history" style={{ marginTop: 8, paddingLeft: 18, fontSize: 13 }}>
      {rows.map((h, i) => (
        <li key={i} style={{ marginBottom: 6 }}>
          {h.from_status && h.from_status !== h.to_status ? `${stageLabel(h.from_status)} → ` : ""}
          {stageLabel(h.to_status)}
          {h.to_sub_status && ` (${subStatusLabel(h.to_sub_status)})`}
          {h.outcome_label && (
            <>
              {" "}
              <span className={isTerminal(h.outcome) ? "status error" : "status pending"}>{h.outcome_label}</span>
            </>
          )}
          {h.changed_by && ` · ${h.changed_by}`} · <LocalTime value={h.created_at} time />
          {(h.notes || h.reason) && <div className="muted history-note">{h.notes || `Reason: ${h.reason}`}</div>}
        </li>
      ))}
    </ol>
  );
}
