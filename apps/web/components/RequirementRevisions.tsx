"use client";
import { useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { REQUIREMENTS_URL, type RevisionDetail, type RevisionItem, type RevisionPage, revisionText } from "@/lib/recruiterRequirements";

/** pob-002 (DEC-SCOPE-405 R5): the requirement's revisions, newest first. "View revision n" reads that revision's values and what changed
 *  against an earlier revision (the one before it unless another is chosen). The API leaves out client terms the caller may not see.
 *  The page re-keys it after a save (the requirement's updated_at), so it re-reads. */
export default function RequirementRevisions({ requirementId }: { requirementId: string }) {
  const [page, setPage] = useState<RevisionPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const headingId = `${useId()}-revisions`;
  const url = `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/revisions`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(`${url}?limit=100`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: RevisionPage) => {
        if (!Array.isArray(body?.items)) throw new Error("shape");
        setPage(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, retry]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Revisions</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the revisions.</p>
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </div>
      ) : page === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading revisions…</p>
      ) : page.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No revisions yet. Each save that changes the requirement adds one.</p>
      ) : (
        <ul aria-label="Revisions" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {page.items.map((item) => (
            <Revision key={item.revision} item={item} url={url} others={page.items.map((i) => i.revision).filter((n) => n < item.revision)}
              open={open === item.revision} onToggle={() => setOpen((n) => (n === item.revision ? null : item.revision))} />
          ))}
        </ul>
      )}
      {page && page.total > page.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {page.items.length} of {page.total} revisions.</p>}
    </section>
  );
}

function Revision({ item, url, others, open, onToggle }: { item: RevisionItem; url: string; others: number[]; open: boolean; onToggle: () => void }) {
  const detailId = `${useId()}-revision`;
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 4, fontSize: 14 }} aria-label={`Revision ${item.revision}`}>
      <span>
        <strong>Revision {item.revision}</strong> · <LocalTime value={item.created_at} time /> ·{" "}
        <span className="muted">by {item.author ? item.author.full_name : "the system"}</span>
      </span>
      {item.reason && <span style={{ overflowWrap: "anywhere" }}>Reason: {item.reason}</span>}
      <span className="muted" style={{ overflowWrap: "anywhere" }}>
        {item.revision === 1 && item.changed_fields.length === 0 ? "The requirement as first recorded" : `Changed: ${item.changed_fields.map((f) => f.label).join(", ") || "—"}`}
      </span>
      <div>
        <button type="button" className="btn secondary small" aria-expanded={open} aria-controls={detailId} onClick={onToggle}>
          {open ? `Hide revision ${item.revision}` : `View revision ${item.revision}`}
        </button>
      </div>
      <div id={detailId}>{open && <RevisionView url={url} revision={item.revision} others={others} />}</div>
    </li>
  );
}

function RevisionView({ url, revision, others }: { url: string; revision: number; others: number[] }) {
  const [compareTo, setCompareTo] = useState<number | null>(others[0] ?? null);
  const [detail, setDetail] = useState<RevisionDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const selectId = `${useId()}-compare`;

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setFailed(false);
    const query = compareTo ? `?compare_to=${compareTo}` : "";
    fetch(`${url}/${revision}${query}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: RevisionDetail) => {
        if (!Array.isArray(body?.values)) throw new Error("shape");
        setDetail(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [url, revision, compareTo]);

  if (failed) return <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load revision {revision}.</p>;
  return (
    <div style={{ display: "grid", gap: 8, marginTop: 4 }}>
      {others.length > 0 && (
        <div className="field" style={{ maxWidth: 260 }}>
          <label htmlFor={selectId}>Compare with</label>
          <select id={selectId} value={compareTo ?? ""} onChange={(e) => setCompareTo(Number(e.target.value))}>
            {others.map((n) => <option key={n} value={n}>Revision {n}</option>)}
          </select>
        </div>
      )}
      {detail === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading revision {revision}…</p>
      ) : (
        <>
          {detail.changes && (
            <div>
              <strong>Changes from revision {detail.compared_to}</strong>
              {detail.changes.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>No differences.</p>
              ) : (
                <ul aria-label={`Changes from revision ${detail.compared_to}`} style={{ margin: 0, paddingLeft: 18, overflowWrap: "anywhere" }}>
                  {detail.changes.map((c) => <li key={c.field}>{c.label}: {revisionText(c.before)} → {revisionText(c.after)}</li>)}
                </ul>
              )}
            </div>
          )}
          <details>
            <summary>All values in revision {revision}</summary>
            <dl style={{ margin: "8px 0 0", display: "grid", gridTemplateColumns: "minmax(140px, max-content) 1fr", gap: "4px 12px", overflowWrap: "anywhere" }}>
              {detail.values.map((v) => (
                <div key={v.field} style={{ display: "contents" }}>
                  <dt className="muted">{v.label}</dt>
                  <dd style={{ margin: 0, whiteSpace: "pre-line" }}>{revisionText(v.value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
    </div>
  );
}
