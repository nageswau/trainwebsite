"use client";
import { useEffect, useState } from "react";

import FollowUpForm from "@/components/FollowUpForm";
import FollowUpItem from "@/components/FollowUpItem";
import { getPage } from "@/lib/telecallerCatalogue";
import { leadFollowUpsUrl, type FollowUp } from "@/lib/telecallerFollowUps";
import type { Page } from "@/lib/apiErrors";

/** tel-011 (spec §4; F2, F4, F5): the lead page's follow-ups -- open ones by due time, then done / cancelled. `canWrite` (the lead's
 *  telecaller, lead not handed over or closed) offers Add; each item's own `can_change` offers its actions. A stage move made with a new
 *  follow-up is reported up, so the page header and activity follow. */
export default function LeadFollowUps({ leadId, leadStage, canWrite, refresh = 0, onStageChanged }: {
  leadId: string; leadStage: string; canWrite: boolean; refresh?: number; onStageChanged: (stage: string) => void;
}) {
  const [data, setData] = useState<Page<FollowUp> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<FollowUp>(leadFollowUpsUrl(leadId), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [leadId, leadStage, version, refresh]); // a stage change elsewhere (closing cancels open follow-ups, F4) or a call's follow-up re-reads

  const changed = (fu: FollowUp, text: string) => {
    setNotice({ text, failed: false });
    if (fu.lead.status !== leadStage) onStageChanged(fu.lead.status); // the new stage re-reads the list
    else reload();
  };

  return (
    <section aria-labelledby="lead-follow-ups-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-follow-ups-heading" style={{ margin: 0 }}>Follow-ups</h3>
        {canWrite && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Add follow-up</button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {adding && (
        <FollowUpForm leadId={leadId} leadStage={leadStage} onCancel={() => setAdding(false)}
          onSaved={(fu) => { setAdding(false); changed(fu, "Follow-up added."); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading follow-ups…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No follow-ups yet.</p>
      ) : (
        <ul aria-label="Follow-ups" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((fu) => (
            <FollowUpItem key={fu.id} followUp={fu} onChanged={changed} onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && (
        <p className="muted" style={{ fontSize: 13 }}>Showing {data.items.length} of {data.total} follow-ups.</p>
      )}
    </section>
  );
}
