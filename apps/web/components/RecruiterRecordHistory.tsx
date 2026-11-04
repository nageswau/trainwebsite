"use client";
import { useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { type AuditChanges, changeText } from "@/lib/auditLog";
import { actionLabel, type HistoryItem, historyPageUrl, humanise, isHistoryPage } from "@/lib/recruiterHistory";

/** hrc-004 (DEC-SCOPE-372 B7): the record's Change history, newest first -- who changed what, from what to what, and when. Compensation
 *  and contact values are never stored, so they read "changed (value hidden)". The page re-keys it after a save, so it re-reads. */
export default function RecruiterRecordHistory({ url }: { url: string }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const headingId = `${useId()}-history`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailed(false);
    fetch(historyPageUrl(url, offset), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => {
        if (!isHistoryPage(body)) throw new Error("shape");
        setTotal(body.total);
        setItems((shown) => [...shown.slice(0, offset), ...body.items]);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFailed(true);
        setLoading(false);
      });
    return () => controller.abort();
  }, [url, offset, retry]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Change history</h3>
      {items.length > 0 && (
        <ul aria-label="Change history" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {items.map((item) => <Entry key={item.id} item={item} />)}
        </ul>
      )}
      {loading ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading history…</p>
      ) : failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the history.</p>
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </div>
      ) : items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No changes recorded yet.</p>
      ) : items.length < total && (
        <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setOffset(items.length)}>
          Show older changes
        </button>
      )}
    </section>
  );
}

function Entry({ item }: { item: HistoryItem }) {
  const label = actionLabel(item.action);
  const changes = Object.entries(item.changes ?? {});
  return (
    <li aria-label={label} className="action-card" style={{ listStyle: "none", gap: 4, fontSize: 14 }}>
      <span>
        <strong>{label}</strong> · <LocalTime value={item.created_at} time /> ·{" "}
        <span className="muted">by {item.actor ? item.actor.full_name : "the system"}</span>
      </span>
      {changes.length > 0 ? (
        <ul aria-label="Changed fields" style={{ margin: 0, paddingLeft: 18, overflowWrap: "anywhere" }}>
          {changes.map(([field, change]) => <li key={field}>{humanise(field)}: {changeText(field === "status" ? statusWords(change) : change)}</li>)}
        </ul>
      ) : item.fields?.length ? (
        <span className="muted" style={{ overflowWrap: "anywhere" }}>
          {item.action.endsWith(".create") ? "Fields set" : "Changed"}: {item.fields.map(humanise).join(", ")}
        </span>
      ) : null}
    </li>
  );
}

/** A status is stored as its key ("on_hold"); shown as words. */
const statusWords = (change: AuditChanges[string]): AuditChanges[string] =>
  change === "changed" ? change : [change[0] === null ? null : humanise(String(change[0])), change[1] === null ? null : humanise(String(change[1]))];
