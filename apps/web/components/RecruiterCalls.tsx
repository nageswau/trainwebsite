"use client";
import { useEffect, useId, useState } from "react";

import RecruiterCallForm from "@/components/RecruiterCallForm";
import type { ContactOption } from "@/components/RecruiterFollowUpForm";
import { sendRequest, type Page } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { type CallParty, callUrl, type LogCallResult, partyCallsUrl, type RecCall } from "@/lib/recruiterCalls";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";
import { formatDuration } from "@/lib/telecallerCalls";
import { getPage } from "@/lib/telecallerCatalogue";

type Notice = { text: string; failed: boolean } | null;
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** One call with Edit / Delete when the API says the viewer may change it (CA4: the caller, on its IST day). */
function CallItem({ call, party, onEdited, onDeleted, onRefused }: {
  call: RecCall; party: CallParty; onEdited: () => void; onDeleted: () => void; onRefused: (message: string) => void;
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

  const details = [
    formatSchoolDateTime(call.occurred_at, true), call.duration_seconds != null ? formatDuration(call.duration_seconds) : null,
    call.direction === "incoming" ? "Incoming" : "Outgoing", call.caller.full_name,
  ].filter(Boolean).join(" · ");
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`}>{call.outcome_label}</strong>
        <span className={`badge${call.connected ? "" : " status error"}`}>{call.connected ? "Connected" : "Not connected"}</span>
        {call.contact && <span style={{ overflowWrap: "anywhere" }}>with {call.contact.name}</span>}
      </div>
      <p className="muted" style={{ margin: 0 }}>{details}</p>
      {call.notes && <p style={{ ...TEXT, margin: 0 }}>{call.notes}</p>}
      {mode === "edit" && (
        <RecruiterCallForm party={party} call={call} onCancel={() => setMode("view")} onEdited={() => { setMode("view"); onEdited(); }} />
      )}
      {mode === "delete" && (
        <div role="group" aria-label="Confirm delete" className="actions">
          <span>Delete this call? Any follow-up it added stays.</span>
          <button type="button" className="btn small" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Yes, delete"}</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("view")}>Keep it</button>
        </div>
      )}
      {mode === "view" && call.can_change && (
        <div className="actions">
          <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit<span className="visually-hidden"> call</span></button>
          <button type="button" className="btn secondary small" onClick={() => setMode("delete")}>Delete<span className="visually-hidden"> call</span></button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </li>
  );
}

/** rec-025 (spec §4): the Calls section of a company (its contacts' calls) or a candidate, newest first. `canWrite` (the company's
 *  `can_edit`, or a candidate writer on an active candidate) offers Log call; a contact call picks one of the company's active contacts.
 *  Every log, edit or delete is reported up (`onChanged`, with the log's result), so Last contacted and the follow-ups re-read. */
export default function RecruiterCalls({ party, canWrite, onChanged }: { party: CallParty; canWrite: boolean; onChanged?: (result?: LogCallResult) => void }) {
  const [data, setData] = useState<Page<RecCall> | null>(null);
  const [contacts, setContacts] = useState<ContactOption[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const headingId = `${useId()}-calls`;
  const reload = () => setVersion((n) => n + 1);
  const url = partyCallsUrl(party);
  const companyId = party.kind === "contact" ? party.companyId : null;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecCall>(url, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, version]);

  // The contact picker: the company's active contacts, re-read each time the form opens (a contact may have been added meanwhile).
  useEffect(() => {
    if (!companyId || !canWrite || !adding) return;
    const controller = new AbortController();
    fetch(contactsOf(companyId), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => isContactList(body) && setContacts(body.items.filter((c) => c.active).map((c) => ({ id: c.id, name: c.name }))))
      .catch(() => undefined); // the form then offers no contacts and the API's 422 explains
    return () => controller.abort();
  }, [companyId, canWrite, adding]);

  const done = (text: string, result?: LogCallResult) => {
    setNotice({ text, failed: false });
    reload();
    onChanged?.(result);
  };
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={headingId} style={{ margin: 0 }}>Calls</h3>
        {canWrite && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Log call</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && canWrite && (
        <RecruiterCallForm party={party} contacts={contacts} onCancel={() => setAdding(false)}
          onLogged={(result) => { setAdding(false); done(result.follow_up_id ? "Call logged. Follow-up added." : "Call logged.", result); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the calls.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading calls…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No calls logged yet.</p>
      ) : (
        <ul aria-label="Calls" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((call) => (
            <CallItem key={call.id} call={call} party={party} onEdited={() => done("Call updated.")} onDeleted={() => done("Call deleted.")}
              onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} calls.</p>}
    </section>
  );
}
