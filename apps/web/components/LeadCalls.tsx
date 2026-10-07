"use client";
import { useEffect, useId, useState } from "react";

import CallLogForm from "@/components/CallLogForm";
import { sendRequest, type Page } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { getPage } from "@/lib/telecallerCatalogue";
import { callUrl, formatDuration, leadCallsUrl, type LeadCall, type LogCallResult } from "@/lib/telecallerCalls";

type Notice = { text: string; failed: boolean } | null;
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** One call with Edit / Delete when the API says the viewer may change it (CL4: the caller, on its IST day). */
function CallItem({ call, leadId, leadStage, onEdited, onDeleted, onRefused }: {
  call: LeadCall; leadId: string; leadStage: string; onEdited: (call: LeadCall) => void; onDeleted: () => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "delete">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function remove() {
    setBusy(true);
    setFailure(null);
    const result = await sendRequest(callUrl(call.id), { method: "DELETE" });
    setBusy(false);
    if (result.ok) return onDeleted();
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    setFailure(kind === "retry" || kind === "offline" ? SAVE_FAILED : result.message);
  }

  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`}>{call.outcome_label}</strong>
        <span className={`badge${call.connected ? "" : " status error"}`}>{call.connected ? "Connected" : "Not connected"}</span>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {formatSchoolDateTime(call.occurred_at, true)} · {formatDuration(call.duration_seconds)} · {call.call_type === "incoming" ? "Incoming" : "Outgoing"} · {call.caller.full_name}
      </p>
      {call.remarks && <p style={{ ...TEXT, margin: 0 }}>{call.remarks}</p>}
      {mode === "edit" && (
        <CallLogForm leadId={leadId} leadStage={leadStage} call={call} onCancel={() => setMode("view")} onEdited={(next) => { setMode("view"); onEdited(next); }} />
      )}
      {mode === "delete" && (
        <div role="group" aria-label="Confirm delete" className="actions">
          <span>Delete this call? The lead&apos;s stage and any follow-up it added stay.</span>
          <button type="button" className="btn small" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Yes, delete"}</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("view")}>Keep it</button>
        </div>
      )}
      {mode === "view" && call.can_change && (
        <div className="actions">
          <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit</button>
          <button type="button" className="btn secondary small" onClick={() => setMode("delete")}>Delete</button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </li>
  );
}

/** tel-010 (spec §5): the lead page's calls, newest first. `canWrite` (the lead's telecaller, lead not handed over or closed) offers Log call;
 *  a bump of `openSignal` (the page's Call button) opens the form too. A logged call's result -- the stage after its effect and any
 *  follow-up it created -- is handed up so the page header, follow-ups and activity follow. */
export default function LeadCalls({ leadId, leadStage, canWrite, openSignal, onLogged }: {
  leadId: string; leadStage: string; canWrite: boolean; openSignal: number; onLogged: (result: LogCallResult) => void;
}) {
  const [data, setData] = useState<Page<LeadCall> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    if (openSignal > 0 && canWrite) {
      setAdding(true);
      setNotice(null);
    }
  }, [openSignal, canWrite]);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<LeadCall>(leadCallsUrl(leadId), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [leadId, version]);

  const done = (text: string) => {
    setNotice({ text, failed: false });
    reload();
  };

  return (
    <section aria-labelledby="lead-calls-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-calls-heading" style={{ margin: 0 }}>Calls</h3>
        {canWrite && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Log call</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && canWrite && (
        <CallLogForm leadId={leadId} leadStage={leadStage} onCancel={() => setAdding(false)}
          onLogged={(result) => { setAdding(false); done("Call logged."); onLogged(result); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the calls.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading calls…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No calls logged yet.</p>
      ) : (
        <ul aria-label="Calls" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((call) => (
            <CallItem key={call.id} call={call} leadId={leadId} leadStage={leadStage} onEdited={() => done("Call updated.")}
              onDeleted={() => done("Call deleted.")} onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} calls.</p>}
    </section>
  );
}
