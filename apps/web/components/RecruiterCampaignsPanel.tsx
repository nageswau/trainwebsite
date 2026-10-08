"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import RecruiterCampaignRow from "@/components/RecruiterCampaignRow";
import RecruiterCatalogueSearch from "@/components/RecruiterCatalogueSearch";
import TelecallerContentList from "@/components/TelecallerContentList";
import { sendJson } from "@/lib/apiErrors";
import { CAMPAIGNS_URL, CATALOGUE_PATH, activeValues, campaignBody, type CatalogueValue, type RecCampaign } from "@/lib/recruiterCatalogue";
import { datesInOrder } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "rec-camp-create-feedback";

// rec-002 (§2 "Campaign"): the manager's recruiter campaigns -- an active lead source, a start date, an optional end date not before
// it -- and the list with search, pager and loading / error+Retry / empty states (the tel-002 campaign screen without a product).
export default function RecruiterCampaignsPanel() {
  const list = useUrlList<RecCampaign>(CAMPAIGNS_URL, "q");
  const [sources, setSources] = useState<CatalogueValue[] | null>(null);
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // a double click must not POST twice
  const focus = useFocusAfterRender();

  const loadSources = useCallback(() => {
    setSourcesFailed(false);
    activeValues("lead-sources").then(setSources).catch(() => setSourcesFailed(true));
  }, []);
  useEffect(loadSources, [loadSources]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const formEl = event.currentTarget;
    const body = campaignBody(new FormData(formEl));
    if (!datesInOrder(body.start_date, body.end_date)) {
      setFeedback({ text: "End date cannot be before the start date", tone: "error" });
      return focus(FEEDBACK_ID);
    }
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(CAMPAIGNS_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${body.name}.`, tone: "success" });
      formEl.reset();
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create campaign</h3>
        <div className="field"><label htmlFor="rec-camp-name">Campaign name (required)</label><input id="rec-camp-name" name="name" required maxLength={160} placeholder="e.g. Q4 IT hiring push" disabled={busy} /></div>
        <div className="field">
          <label htmlFor="rec-camp-source">Lead source (required)</label>
          <select id="rec-camp-source" name="lead_source_id" required defaultValue="" disabled={busy || !sources?.length}>
            <option value="" disabled>{sources === null && !sourcesFailed ? "Loading lead sources…" : "Choose a lead source"}</option>
            {sources?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        {sourcesFailed && (
          <p className="form-error" role="alert">
            Unable to load lead sources. <button type="button" className="btn secondary small" onClick={loadSources}>Retry loading lead sources</button>
          </p>
        )}
        {sources?.length === 0 && <p className="muted" style={{ fontSize: 13 }}>No active lead source — add or reactivate one on the <Link href={`${CATALOGUE_PATH}/lead-sources`}>Lead sources</Link> tab first.</p>}
        <div className="field"><label htmlFor="rec-camp-start">Start date (required)</label><input id="rec-camp-start" name="start_date" type="date" required disabled={busy} /></div>
        <div className="field"><label htmlFor="rec-camp-end">End date</label><input id="rec-camp-end" name="end_date" type="date" disabled={busy} /></div>
        <button className="btn" disabled={busy || !sources?.length}>{busy ? "Creating…" : "Create campaign"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title="Campaigns"
        noun="campaigns"
        list={list}
        notice={notice}
        filter={<RecruiterCatalogueSearch list={list} label="Search campaigns" />}
        createTargetId="rec-camp-name"
        createLabel="Create campaign"
        headers={["Name", "Lead source", "Dates", "Status"]}
      >
        {(items) => items.map((row) => <RecruiterCampaignRow key={row.id} row={row} sources={sources ?? []} onChanged={(text) => { setNotice(text); list.reload(); }} />)}
      </TelecallerContentList>
    </>
  );
}
