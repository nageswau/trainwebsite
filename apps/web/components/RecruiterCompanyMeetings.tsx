"use client";
import { useEffect, useState } from "react";

import RecruiterMeetingForm, { type ContactOption } from "@/components/RecruiterMeetingForm";
import RecruiterMeetingItem from "@/components/RecruiterMeetingItem";
import type { Page } from "@/lib/apiErrors";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";
import { companyMeetingsUrl, LIST_LIMIT, type RecMeeting } from "@/lib/recruiterMeetings";
import { getPage } from "@/lib/telecallerCatalogue";

/** rec-028 (spec §4; MT5, MT9): a company's meetings -- scheduled ones by start, then completed / cancelled. `canWrite` (the company's
 *  `can_edit`) offers Schedule; each item's own `can_change` offers its actions. The active contacts feed the form. Every change is
 *  reported up (`onChanged`): scheduling can move the company's stage (AC1) and an outcome can add a follow-up (AC2). */
export default function RecruiterCompanyMeetings({ companyId, canWrite, onChanged }: { companyId: string; canWrite: boolean; onChanged: () => void }) {
  const [data, setData] = useState<Page<RecMeeting> | null>(null);
  const [contacts, setContacts] = useState<ContactOption[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecMeeting>(`${companyMeetingsUrl(companyId)}?limit=${LIST_LIMIT}`, controller.signal)
      .then(setData)
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [companyId, version]);

  useEffect(() => {
    if (!canWrite) return;
    const controller = new AbortController();
    fetch(contactsOf(companyId), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => isContactList(body) && setContacts(body.items.filter((c) => c.active).map((c) => ({ id: c.id, name: c.name }))))
      .catch(() => undefined); // contacts are optional: without them the form still schedules a meeting
    return () => controller.abort();
  }, [companyId, canWrite]);

  const changed = (text: string) => {
    setNotice({ text, failed: false });
    reload();
    onChanged();
  };

  return (
    <section className="action-card wide" aria-labelledby={`company-${companyId}-meetings`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`company-${companyId}-meetings`} style={{ margin: 0 }}>Meetings</h3>
        {canWrite && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Schedule meeting</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && (
        <RecruiterMeetingForm companyId={companyId} contacts={contacts} onCancel={() => setAdding(false)}
          onSaved={(m) => { setAdding(false); changed(`Meeting ${m.code} scheduled.`); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the meetings.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading meetings…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No meetings yet.</p>
      ) : (
        <ul aria-label="Meetings" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((m) => (
            <RecruiterMeetingItem key={m.id} meeting={m} contacts={contacts} onChanged={(_, text) => changed(text)}
              onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing {data.items.length} of {data.total} meetings.</p>}
    </section>
  );
}
