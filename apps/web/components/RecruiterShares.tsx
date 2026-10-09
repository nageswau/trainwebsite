"use client";
import Link from "next/link";
import { type FormEvent, useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";
import {
  companySharesUrl,
  FEEDBACK_MAX,
  isSharePage,
  isShareItem,
  PAGE_SIZE,
  requirementSharesUrl,
  RESPONSES,
  type Share,
  type ShareItem,
  shareItemUrl,
  type SharePage,
  type ShareResponse,
} from "@/lib/recruiterShares";

type Source = { kind: "requirement"; requirementId: string } | { kind: "company"; companyId: string };
const DELIVERY: Record<string, string> = { queued: "Queued", sending: "Sending", retrying: "Retrying", sent: "Sent", failed: "Failed" };

function ResponseForm({ shareId, item, onSaved, onCancel }: { shareId: string; item: ShareItem; onSaved: (i: ShareItem) => void; onCancel: () => void }) {
  const [response, setResponse] = useState<ShareResponse>(item.response);
  const [feedback, setFeedback] = useState(item.feedback ?? "");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(shareItemUrl(shareId, item.id), "PATCH", { response, feedback: feedback.trim() || null });
    setBusy(false);
    if (outcome.ok && isShareItem(outcome.data)) onSaved(outcome.data);
    else setFailure(outcome.ok ? "Unable to save the response." : outcome.message);
  }

  return (
    <form onSubmit={(e) => void submit(e)} style={{ display: "grid", gap: 8 }} aria-label={`Response for ${item.candidate.name}`}>
      <label htmlFor={`${id}-response`} style={{ display: "grid", gap: 4 }}>
        Company response
        <select id={`${id}-response`} value={response} onChange={(e) => setResponse(e.target.value as ShareResponse)}>
          {RESPONSES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
      </label>
      <label htmlFor={`${id}-feedback`} style={{ display: "grid", gap: 4 }}>
        Recruiter feedback (optional)
        <textarea id={`${id}-feedback`} rows={2} maxLength={FEEDBACK_MAX} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
      </label>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save response"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function Item({ share, item, onSaved }: { share: Share; item: ShareItem; onSaved: (i: ShareItem) => void }) {
  const [editing, setEditing] = useState(false);
  return (
    <li style={{ display: "grid", gap: 4, paddingTop: 6, borderTop: "1px solid var(--line)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(item.candidate.id)}`} style={{ ...LINK_STYLE, fontWeight: 600, overflowWrap: "anywhere" }}>{item.candidate.name}</Link>
        <span className="muted" style={{ fontSize: 13 }}>{item.candidate.code}</span>
        <span className="badge">{item.response_label}</span>
        {!item.has_resume && <span className="muted" style={{ fontSize: 13 }}>No resume shared</span>}
      </div>
      {item.feedback && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>Feedback: {item.feedback}</p>}
      {item.responded_by && item.responded_at && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Response by {item.responded_by.full_name}, <LocalTime value={item.responded_at} time /></p>
      )}
      {share.can_respond && !editing && (
        <span>
          <button type="button" className="btn secondary small" onClick={() => setEditing(true)}>
            Record response<span className="visually-hidden"> for {item.candidate.name}</span>
          </button>
        </span>
      )}
      {editing && <ResponseForm shareId={share.id} item={item} onCancel={() => setEditing(false)} onSaved={(next) => { setEditing(false); onSaved(next); }} />}
    </li>
  );
}

function ShareCard({ share, showRequirement, onItem }: { share: Share; showRequirement: boolean; onItem: (i: ShareItem) => void }) {
  const id = useId();
  const delivery = share.message?.delivery_status;
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`}>
          {share.channel_label}{share.contact ? ` to ${share.contact.name}` : ""} · {share.items.length} profile{share.items.length === 1 ? "" : "s"}
        </strong>
        {delivery && <span className="badge">Email {DELIVERY[delivery] ?? delivery}</span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        <LocalTime value={share.created_at} time /> by {share.shared_by.full_name}
        {showRequirement && <> · {share.requirement.code} {share.requirement.title}</>}
      </p>
      {share.note && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>Note: {share.note}</p>}
      <ul aria-label="Shared candidates" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
        {share.items.map((item) => <Item key={item.id} share={share} item={item} onSaved={onItem} />)}
      </ul>
    </li>
  );
}

/** rec-019 (spec §5; S9, S14): the shares of a requirement or a company, newest first, each with its candidates, the company's response
 *  and the recruiter's feedback. Writers (`can_respond`) record a response; the manager and the assigned BDM read. `refreshKey` re-reads
 *  after a share made elsewhere on the page. */
export default function RecruiterShares({ source, refreshKey = 0 }: { source: Source; refreshKey?: number }) {
  const [data, setData] = useState<SharePage | null>(null);
  const [failed, setFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [reloads, setReloads] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const headingId = `${useId()}-shares`;
  const url = source.kind === "requirement" ? requirementSharesUrl(source.requirementId, offset) : companySharesUrl(source.companyId, offset);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(url, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isSharePage(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, reloads, refreshKey]);

  const saved = (next: ShareItem) => {
    setData((d) => d && { ...d, items: d.items.map((s) => ({ ...s, items: s.items.map((i) => (i.id === next.id ? next : i)) })) });
    setNotice(`Response saved for ${next.candidate.name}.`);
  };
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Shared profiles{data ? ` (${data.total})` : ""}</h3>
      <div role="status" aria-live="polite">{notice && <p className="form-message" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}</div>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the shared profiles.</p>
          <button type="button" className="btn secondary small" onClick={() => setReloads((n) => n + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading shared profiles…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No profiles shared yet. Select candidates and choose Share to send them to the company.</p>
      ) : (
        <>
          <ul aria-label="Shares" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((share) => <ShareCard key={share.id} share={share} showRequirement={source.kind === "company"} onItem={saved} />)}
          </ul>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Shared profile pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(data.offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
