"use client";
import { useRef, useState } from "react";

import RecruiterTemplateRow, { RecruiterTemplateFields, templateBody } from "@/components/RecruiterTemplateRow";
import TelecallerContentList from "@/components/TelecallerContentList";
import { sendJson } from "@/lib/apiErrors";
import { TEMPLATES_URL, type Channel, type RecTemplate } from "@/lib/recruiterMessages";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "rtpl-create-feedback";
const CHANNELS = ["whatsapp", "email"] as const;

// rec-026 (MS1-MS3): the placement manager's WhatsApp and email templates (EVID-018 §19). Create form + list filtered by channel; each row
// edits inline, deactivates / reactivates and previews with sample values. The tel-012 library layout, reused.
export default function RecruiterTemplatesPanel() {
  const list = useUrlList<RecTemplate>(TEMPLATES_URL, "channel", CHANNELS);
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [formKey, setFormKey] = useState(0); // remounts the fields (and their controlled message) after a create
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const fields = templateBody(new FormData(event.currentTarget), channel);
    setBusy(true);
    const outcome = await sendJson(TEMPLATES_URL, "POST", { channel, ...fields });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${fields.name}.`, tone: "success" });
      setFormKey((k) => k + 1);
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create template</h3>
        <RecruiterTemplateFields key={formKey} idPrefix="rtpl-new" channel={channel} onChannel={setChannel} disabled={busy} />
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create template"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title="Templates"
        noun="templates"
        list={list}
        notice={notice}
        createTargetId="rtpl-new-channel"
        createLabel="Create template"
        headers={["Name", "Channel", "Kind", "Status"]}
        filter={
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="rtpl-filter">Show</label>
            <select id="rtpl-filter" value={list.filter} onChange={(e) => list.go(e.target.value, 0)}>
              <option value="">All channels</option><option value="whatsapp">WhatsApp</option><option value="email">Email</option>
            </select>
          </div>
        }
      >
        {(items) => items.map((t) => <RecruiterTemplateRow key={t.id} row={t} onChanged={(text) => { setNotice(text); list.reload(); }} />)}
      </TelecallerContentList>
    </>
  );
}
