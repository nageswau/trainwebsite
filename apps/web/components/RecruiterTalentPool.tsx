"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card } from "@/components/RecruiterFindCandidates";
import RecruiterTalentPoolForm from "@/components/RecruiterTalentPoolForm";
import { detailMessage } from "@/lib/apiErrors";
import { findHref, formOf, isPoolMembers, MEMBERS_PAGE, membersUrl, type PoolMembers, ruleText } from "@/lib/recruiterPools";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const noShortlist = () => undefined; // members are listed read-only here; shortlisting happens in Find Candidates (P8)
const EDIT_ID = "talent-pool-edit";

/** rec-015: one pool -- its rule, its members (computed now, newest first) and, for a placement manager, Edit. The page frame holds
 *  the "Back to talent pools" link (QA-04). */
export default function RecruiterTalentPool({ poolId }: { poolId: string }) {
  const [data, setData] = useState<PoolMembers | null>(null);
  const [error, setError] = useState<{ message: string; retry: boolean } | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [version, setVersion] = useState(0);
  const focus = useFocusAfterRender(); // QA-02: back to Edit pool once the form has closed

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch(membersUrl(poolId, offset), { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (response.ok && isPoolMembers(body)) return setData(body);
        setData(null);
        const broken = response.status >= 500;
        setError({ message: broken ? "Unable to load this pool." : detailMessage(body?.detail, "Unable to load this pool."), retry: broken });
      })
      .catch(() => controller.signal.aborted || setError({ message: "Unable to load this pool. Check your connection and try again.", retry: true }))
      .finally(() => controller.signal.aborted || setLoading(false));
    return () => controller.abort();
  }, [poolId, offset, version]);

  if (error) {
    return (
      <div className="action-card" role="alert">
        <p style={{ margin: 0 }}>{error.message}</p>
        {error.retry && <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setVersion((v) => v + 1)}>Try again</button>}
      </div>
    );
  }
  if (!data) return <p className="muted" role="status">Loading pool…</p>;

  const { pool, can_manage: canManage } = data;
  const find = findHref(pool);
  const closeForm = () => {
    setEditing(false);
    focus(EDIT_ID);
  };
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Talent pool{pool.active ? "" : " · Inactive"}</div>
          <h2 style={{ overflowWrap: "anywhere" }}>{pool.name}</h2>
          <p className="muted" style={{ overflowWrap: "anywhere" }}>{ruleText(pool)}</p>
        </div>
        <div className="actions" style={{ gap: 8 }}>
          {find && <Link className="btn secondary" href={find}>Refine in Find Candidates</Link>}
          {canManage && !editing && (
            <button id={EDIT_ID} type="button" className="btn" onClick={() => { setEditing(true); setSaved(false); }}>Edit pool</button>
          )}
        </div>
      </div>
      {pool.unavailable.length > 0 && (
        <div className="action-card" role="note" style={{ borderLeft: "4px solid var(--warning, #b45309)" }}>
          <p style={{ margin: 0, fontWeight: 700 }}>Some skills in this pool are no longer in the Skills Master: {pool.unavailable.join(", ")}.</p>
          <p className="muted" style={{ margin: 0 }}>
            They match nobody, so the pool may be smaller than expected.{canManage ? " Edit the pool to replace them." : " Ask your placement manager to update it."}
          </p>
        </div>
      )}
      {editing && (
        <RecruiterTalentPoolForm initial={formOf(pool)} poolId={pool.id} onCancel={closeForm}
          onSaved={() => { closeForm(); setSaved(true); setOffset(0); setVersion((v) => v + 1); }} />
      )}
      {saved && <p className="form-message" role="status" style={{ margin: 0 }}>Pool saved. Members are recalculated from the new rule.</p>}
      <section aria-label="Pool members" aria-busy={loading} style={{ display: "grid", gap: 12 }}>
        <div role="status"><h2 style={{ fontSize: 22, margin: 0 }}>{data.total === 1 ? "1 candidate" : `${data.total} candidates`}</h2></div>
        {data.total === 0 ? (
          <p className="muted">No candidates match this pool yet. Candidates join automatically when their skills and experience match.</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No candidates on this page. <button type="button" className="btn secondary small" onClick={() => setOffset(0)}>Go to the first page</button></p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
            {data.items.map((c) => <Card key={c.id} c={c} writes={false} requirement={null} onShortlist={noShortlist} matchNote="matches this pool" />)}
          </ul>
        )}
        {data.total > MEMBERS_PAGE && data.items.length > 0 && (
          <nav aria-label="Member pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
            <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - MEMBERS_PAGE))}>Previous</button>
            <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(data.offset + MEMBERS_PAGE)}>Next</button>
          </nav>
        )}
      </section>
    </div>
  );
}
