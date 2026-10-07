"use client";

import { type FormEvent, useId, useState } from "react";

import { isRequestBody, sendJson } from "@/lib/apiErrors";
import { handoverUrl } from "@/lib/leadHandover";
import { leadUrl, type PersonRef, type TelecallerLeadDetail } from "@/lib/telecallerLeads";

type Notice = { text: string; failed: boolean } | null;

/** tel-018 (spec §4; HO4): "Assign to counselor" -- the lead's telecaller hands it to an active counselor of its division; a manager
 *  may change the counselor later. The counselors (tel-016's booking options) are read only when the form opens. The API decides. */
export default function LeadHandoverForm({ lead, onDone }: { lead: TelecallerLeadDetail; onDone: (lead: TelecallerLeadDetail) => void }) {
  const id = useId();
  const [counselors, setCounselors] = useState<PersonRef[] | "loading" | "failed" | null>(null);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const changing = !!lead.counselor;

  async function open() {
    setCounselors("loading");
    setNotice(null);
    try {
      const response = await fetch(leadUrl(lead.id, "/appointment-options"));
      const data = response.ok ? await response.json() : null;
      if (!Array.isArray(data?.counselors)) throw new Error();
      setCounselors((data.counselors as PersonRef[]).filter((c) => c.id !== lead.counselor?.id));
    } catch {
      setCounselors("failed");
    }
  }

  function close() {
    setCounselors(null);
    setChoice("");
    setNotice(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!choice) return setNotice({ text: "Choose a counselor.", failed: true });
    setBusy(true);
    const outcome = await sendJson(handoverUrl(lead.id), "POST", { counselor_id: choice });
    setBusy(false);
    if (!outcome.ok || !isRequestBody(outcome.data)) return setNotice({ text: outcome.ok ? "Unable to hand the lead over." : outcome.message, failed: true });
    close();
    onDone(outcome.data as unknown as TelecallerLeadDetail);
  }

  const label = changing ? "Change counselor" : "Assign to counselor";
  if (counselors === null) return <button type="button" className="btn secondary small" onClick={open}>{label}</button>;
  return (
    <form onSubmit={submit} noValidate aria-label={label} style={{ display: "grid", gap: 8, maxWidth: "24rem" }}>
      {counselors === "loading" && <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading counselors…</p>}
      {counselors === "failed" && <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the counselors.</p>}
      {Array.isArray(counselors) && (
        counselors.length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>No other active counselor in this division.</p>
        ) : (
          <div className="field">
            <label htmlFor={`${id}-counselor`}>Counselor</label>
            <select id={`${id}-counselor`} value={choice} disabled={busy} aria-required onChange={(e) => { setChoice(e.target.value); setNotice(null); }}>
              <option value="">Choose a counselor</option>
              {counselors.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
            </select>
          </div>
        )
      )}
      {!changing && Array.isArray(counselors) && counselors.length > 0 && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>The counselor takes over the lead. You keep read access and its open follow-ups are cancelled.</p>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {Array.isArray(counselors) && counselors.length > 0 && <button type="submit" className="btn small" disabled={busy}>{busy ? "Handing over…" : "Hand over"}</button>}
        <button type="button" className="btn secondary small" disabled={busy} onClick={close}>Cancel</button>
      </div>
    </form>
  );
}
