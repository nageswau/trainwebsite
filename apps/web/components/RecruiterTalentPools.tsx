"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import RecruiterTalentPoolForm from "@/components/RecruiterTalentPoolForm";
import { detailMessage } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { EMPTY_POOL, isPoolList, poolPath, type PoolList, POOLS_URL, ruleText } from "@/lib/recruiterPools";

/** rec-015: every active pool with its member count; a placement manager also sees inactive pools (on request) and creates pools. */
export default function RecruiterTalentPools() {
  const router = useRouter();
  const [data, setData] = useState<PoolList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inactive, setInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetch(`${POOLS_URL}?include_inactive=${inactive}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (response.ok && isPoolList(body)) return setData(body);
        setData(null);
        setError(response.status >= 500 ? "Unable to load talent pools." : detailMessage(body?.detail, "Unable to load talent pools."));
      })
      .catch(() => controller.signal.aborted || setError("Unable to load talent pools. Check your connection and try again."));
    return () => controller.abort();
  }, [inactive, version]);

  if (error) {
    return (
      <div className="action-card" role="alert">
        <p style={{ margin: 0 }}>{error}</p>
        <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setVersion((v) => v + 1)}>Try again</button>
      </div>
    );
  }
  if (!data) return <p className="muted" role="status">Loading talent pools…</p>;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {data.can_manage && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> Show inactive pools
          </label>
          {!creating && <button type="button" className="btn" onClick={() => setCreating(true)}>+ New pool</button>}
        </div>
      )}
      {creating && (
        <RecruiterTalentPoolForm initial={EMPTY_POOL} onCancel={() => setCreating(false)} onSaved={(pool) => router.push(poolPath(pool.id))} />
      )}
      {data.items.length === 0 ? (
        <div className="action-card">
          <p style={{ margin: 0 }}>No talent pools yet.</p>
          <p className="muted" style={{ margin: 0 }}>{data.can_manage ? "Create a pool to group candidates by skill or experience." : "Your placement manager creates the pools."}</p>
        </div>
      ) : (
        <ul aria-label="Talent pools" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(17rem, 1fr))" }}>
          {data.items.map((pool) => (
            <li key={pool.id} className="action-card" style={{ gap: 8 }}>
              <h3 style={{ margin: 0, fontSize: 18 }}>
                <Link href={poolPath(pool.id)} style={LINK_STYLE}>{pool.name}</Link>
              </h3>
              <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>{ruleText(pool)}</p>
              <p style={{ margin: 0, fontWeight: 700 }}>{pool.members === 1 ? "1 candidate" : `${pool.members} candidates`}</p>
              {(!pool.active || pool.unavailable.length > 0) && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {!pool.active && <span className="badge">Inactive</span>}
                  {pool.unavailable.length > 0 && <span className="badge" title={`No longer in the Skills Master: ${pool.unavailable.join(", ")}`}>Needs attention</span>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
