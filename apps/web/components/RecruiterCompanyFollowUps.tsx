"use client";
import { useEffect, useState } from "react";

import type { ContactOption } from "@/components/RecruiterFollowUpForm";
import RecruiterFollowUpForm from "@/components/RecruiterFollowUpForm";
import RecruiterFollowUpItem from "@/components/RecruiterFollowUpItem";
import type { Page } from "@/lib/apiErrors";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";
import { companyFollowUpsUrl, LIST_LIMIT, type RecFollowUp } from "@/lib/recruiterFollowUps";
import { getPage } from "@/lib/telecallerCatalogue";

/** rec-024 (spec §4; FU3, FU6): a company's follow-ups -- open ones by due time, then done / cancelled. `canWrite` (the company's
 *  `can_edit`) offers Add; each item's own `can_change` offers its actions. The active contacts feed the form's contact picker. Every
 *  change is reported up (`onChanged`), so the company's "Next follow-up" and the contacts' follow up. */
export default function RecruiterCompanyFollowUps({ companyId, canWrite, onChanged }: { companyId: string; canWrite: boolean; onChanged: () => void }) {
  const [data, setData] = useState<Page<RecFollowUp> | null>(null);
  const [contacts, setContacts] = useState<ContactOption[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecFollowUp>(`${companyFollowUpsUrl(companyId)}?limit=${LIST_LIMIT}`, controller.signal)
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
      .catch(() => undefined); // the picker is optional: without contacts the form still adds a company follow-up
    return () => controller.abort();
  }, [companyId, canWrite]);

  const changed = (text: string) => {
    setNotice({ text, failed: false });
    reload();
    onChanged();
  };

  return (
    <section className="action-card wide" aria-labelledby={`company-${companyId}-follow-ups`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`company-${companyId}-follow-ups`} style={{ margin: 0 }}>Follow-ups</h3>
        {canWrite && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Add follow-up</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && (
        <RecruiterFollowUpForm companyId={companyId} contacts={contacts} onCancel={() => setAdding(false)}
          onSaved={() => { setAdding(false); changed("Follow-up added."); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading follow-ups…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No follow-ups yet.</p>
      ) : (
        <ul aria-label="Follow-ups" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((fu) => (
            <RecruiterFollowUpItem key={fu.id} followUp={fu} contacts={contacts} onChanged={(_, text) => changed(text)}
              onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing {data.items.length} of {data.total} follow-ups.</p>}
    </section>
  );
}
