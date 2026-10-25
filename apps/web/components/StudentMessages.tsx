"use client";
import { type FormEvent, useId, useMemo, useRef, useState } from "react";

import MessagesSection from "@/components/MessagesSection";
import { localToIso, toLocalInput } from "@/lib/agentTasks";
import { sendJson } from "@/lib/apiErrors";
import { replyUrl, studentMessagesUrl, studentTarget, type StudentApplicationRef, type StudentRecipient } from "@/lib/counselorMessages";
import { CHANNEL_LABEL, type Channel, type Party } from "@/lib/recruiterMessages";
import { BODY_MAX, EMAIL_BODY_MAX, SUBJECT_MAX } from "@/lib/telecallerMessages";

/** ccrm-037 (DEC-SCOPE-273, MT4-MT9): the student 360's Messages -- the shared rec-026/upc-012 section with the student as the only
 *  recipient. "About" ties a send to one of the counselor's applications (it rides on the render query and the send body); changing it
 *  starts the composer afresh, so the text never carries another application's values. Replies arrive outside the platform (no inbound
 *  provider), so the counselor records them by hand (MT7). The Overseas Admin (`canWrite` false) reads only. */
export default function StudentMessages({ studentId, recipient, applications, canWrite }: {
  studentId: string; recipient: StudentRecipient; applications: StudentApplicationRef[]; canWrite: boolean;
}) {
  const [about, setAbout] = useState("");
  const [recorded, setRecorded] = useState(0); // a recorded reply re-mounts the list, so it re-reads
  const [replying, setReplying] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const aboutId = useId();
  const parties = useMemo(
    (): Party[] => [{ kind: "student", id: studentId, name: recipient.name, whatsappTo: recipient.whatsapp_to, email: recipient.email }],
    [studentId, recipient],
  );
  const target = useMemo(() => studentTarget(studentId, about), [studentId, about]);

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {canWrite && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end", justifyContent: "space-between" }}>
          {applications.length > 0 ? (
            <div className="field" style={{ maxWidth: 360, flex: "1 1 240px", margin: 0 }}>
              <label htmlFor={aboutId}>About</label>
              <select id={aboutId} value={about} onChange={(e) => { setAbout(e.target.value); setNotice(null); }}>
                <option value="">General — not about one application</option>
                {applications.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
            </div>
          ) : <span />}
          {!replying && <button type="button" className="btn secondary small" onClick={() => { setReplying(true); setNotice(null); }}>Record a reply</button>}
        </div>
      )}
      {notice && <p className="form-message" role="status" style={{ margin: 0, fontSize: 13 }}>{notice}</p>}
      {canWrite && replying && (
        <ReplyForm studentId={studentId} applicationId={about} onCancel={() => setReplying(false)}
          onRecorded={() => { setReplying(false); setNotice("Reply recorded."); setRecorded((n) => n + 1); }} />
      )}
      <MessagesSection key={`${about}:${recorded}`} listUrl={studentMessagesUrl(studentId)} parties={parties} picker={false} targetFor={() => target}
        canWrite={canWrite} noParties="" />
    </div>
  );
}

function ReplyForm({ studentId, applicationId, onRecorded, onCancel }: {
  studentId: string; applicationId: string; onRecorded: () => void; onCancel: () => void;
}) {
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [received, setReceived] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saving = useRef(false); // a second activation before the re-render must not record twice
  const id = useId();
  const limit = channel === "email" ? EMAIL_BODY_MAX : BODY_MAX;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving.current) return;
    if (!body.trim()) return setError("Enter the reply.");
    saving.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(replyUrl(studentId), "POST", {
      channel, body: body.trim(),
      ...(channel === "email" && subject.trim() ? { subject: subject.trim() } : {}),
      ...(received ? { received_at: localToIso(received) } : {}),
      ...(applicationId ? { application_id: applicationId } : {}),
    });
    saving.current = false;
    setBusy(false);
    if (outcome.ok) return onRecorded();
    setError(outcome.message);
  }

  return (
    <form className="action-card" aria-label="Record a reply" onSubmit={(e) => void submit(e)} style={{ display: "grid", gap: 8 }} noValidate>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Record a reply the student sent you by WhatsApp or email{applicationId ? ", about the application chosen above" : ""}.
      </p>
      <div className="field">
        <label htmlFor={`${id}-channel`}>Channel</label>
        <select id={`${id}-channel`} value={channel} disabled={busy} onChange={(e) => setChannel(e.target.value as Channel)}>
          {(["whatsapp", "email"] as const).map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
        </select>
      </div>
      {channel === "email" && (
        <div className="field">
          <label htmlFor={`${id}-subject`}>Subject (optional)</label>
          <input id={`${id}-subject`} value={subject} maxLength={SUBJECT_MAX} disabled={busy} onChange={(e) => setSubject(e.target.value)} />
        </div>
      )}
      <div className="field">
        <label htmlFor={`${id}-body`}>Reply</label>
        <textarea id={`${id}-body`} rows={4} maxLength={limit} value={body} disabled={busy} aria-describedby={`${id}-count`} onChange={(e) => setBody(e.target.value)} />
        <span id={`${id}-count`} className="muted" style={{ fontSize: 12 }}>{body.length}/{limit} characters</span>
      </div>
      <div className="field">
        <label htmlFor={`${id}-received`}>Received</label>
        <input id={`${id}-received`} type="datetime-local" value={received} max={toLocalInput(new Date().toISOString())} disabled={busy}
          aria-describedby={`${id}-received-hint`} onChange={(e) => setReceived(e.target.value)} />
        <p id={`${id}-received-hint`} className="field-hint">Your local time. Leave empty for now; up to 7 days back.</p>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save reply"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
