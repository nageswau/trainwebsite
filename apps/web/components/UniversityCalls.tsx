"use client";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import UniversityCallForm, { type CallContact } from "@/components/UniversityCallForm";
import type { Page } from "@/lib/apiErrors";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { universityCallsUrl, type UniversityCall } from "@/lib/partnershipComms";
import { formatDuration } from "@/lib/telecallerCalls";
import { getPage } from "@/lib/telecallerCatalogue";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

function CallItem({ call }: { call: UniversityCall }) {
  const id = useId();
  const details = [
    formatSchoolDateTime(call.occurred_at, true), call.duration_seconds != null ? formatDuration(call.duration_seconds) : null,
    call.direction === "incoming" ? "Incoming" : "Outgoing", call.caller.full_name,
  ].filter(Boolean).join(" · ");
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`}>{call.outcome_label}</strong>
        <span className={`badge${call.connected ? "" : " status error"}`}>{call.connected ? "Connected" : "Not connected"}</span>
        <span style={{ overflowWrap: "anywhere" }}>with {call.contact?.name ?? "a removed contact"}</span>
      </div>
      <p className="muted" style={{ margin: 0 }}>{details}</p>
      {call.notes && <p style={{ ...TEXT, margin: 0 }}>{call.notes}</p>}
      {call.next_follow_up_on && <p className="muted" style={{ margin: 0 }}>Next follow-up: {formatCalendarDate(call.next_follow_up_on)}</p>}
    </li>
  );
}

/** upc-012 (UC1, AC3): the Calls section of a university, newest first. `canWrite` (the API's `can_edit_contacts`) offers Log call on one of
 *  the university's contacts; each log re-reads the page so the contact's last interaction moves. Calls are permanent. */
export default function UniversityCalls({ universityId, contacts, canWrite }: { universityId: string; contacts: CallContact[]; canWrite: boolean }) {
  const router = useRouter();
  const [data, setData] = useState<Page<UniversityCall> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const headingId = `${useId()}-calls`;
  const url = universityCallsUrl(universityId);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<UniversityCall>(url, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, version]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={headingId} style={{ margin: 0 }}>Calls</h3>
        {canWrite && !adding && contacts.length > 0 && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Log call</button>
        )}
      </div>
      {canWrite && contacts.length === 0 && <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>Add a contact to log a call.</p>}
      {notice && <p className="form-message" role="status" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}
      {adding && canWrite && (
        <UniversityCallForm contacts={contacts} onCancel={() => setAdding(false)}
          onLogged={() => { setAdding(false); setNotice("Call logged."); reload(); router.refresh(); }} />
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
          {data.items.map((call) => <CallItem key={call.id} call={call} />)}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} calls.</p>}
    </section>
  );
}
