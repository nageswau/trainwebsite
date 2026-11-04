"use client";
import { useEffect, useId, useMemo, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import LocalTime from "@/components/LocalTime";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import {
  isRequirementBody, type Owner, type OwnerChange, type OwnerChangePage, OWNER_ROLE_OPTIONS, ownerChangeText, type OwnerRole, ownerSearch, type Requirement,
  REQUIREMENTS_URL,
} from "@/lib/recruiterRequirements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Changed = (next: Requirement, text: string) => void;
const ROW_STYLE = { listStyle: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 12px" } as const;

/** hrc-006 (DEC-SCOPE-384 O12): the primary, the placement-officer owner and the collaborators. Whoever may manage the owners (the
 *  primary, a placement manager, super_admin -- the API decides) adds and removes them; the primary changes only by Reassign. */
export function OwnersCard({ requirement, onChanged }: { requirement: Requirement; onChanged: Changed }) {
  const [role, setRole] = useState<OwnerRole>("collaborator");
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [removing, setRemoving] = useState<Owner | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const headingId = `requirement-${requirement.id}-owners`;
  const manage = requirement.permissions.can_manage_owners;
  const search = useMemo(() => ownerSearch(requirement.id, role), [requirement.id, role]);
  const removeId = (o: Owner) => `${headingId}-remove-${o.user.id}`;

  async function send(promise: Promise<Awaited<ReturnType<typeof sendJson>>>, done: string) {
    setBusy(true);
    setFailure(null);
    const outcome = await promise;
    setBusy(false);
    setRemoving(null);
    if (outcome.ok && isRequirementBody(outcome.data)) {
      setPicked(null);
      onChanged(outcome.data.requirement, done);
    } else setFailure(outcome.ok ? "Unable to change the owners." : outcome.message);
  }

  const add = () => {
    if (!picked) return;
    const label = OWNER_ROLE_OPTIONS.find((o) => o.key === role)!.label;
    void send(sendJson(`${REQUIREMENTS_URL}/${requirement.id}/assignments`, "POST", { user_id: picked.id, role }), `${picked.label} added as ${label}.`);
  };
  const remove = (o: Owner) =>
    void send(sendRequest(`${REQUIREMENTS_URL}/${requirement.id}/assignments/${o.user.id}`, { method: "DELETE" }), `${o.user.full_name} removed from the owners.`);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId}>Owners</h3>
      <ul style={{ margin: 0, padding: 0, display: "grid", gap: 8 }}>
        <li style={ROW_STYLE}>
          {requirement.assigned_recruiter ? <strong>{requirement.assigned_recruiter.full_name}</strong> : <span className="muted">No primary owner yet</span>}
          <span className="badge">Primary owner</span>
        </li>
        {requirement.owners.map((o) => (
          <li key={o.user.id} style={ROW_STYLE}>
            <strong>{o.user.full_name}</strong>
            <span className="badge">{o.role_label}</span>
            <span className="muted" style={{ overflowWrap: "anywhere" }}>{o.user.email}</span>
            <span className="muted" style={{ fontSize: 13 }}>
              added by {o.added_by?.full_name ?? "the system"} on <LocalTime value={o.added_at} />
            </span>
            {manage && (
              <button id={removeId(o)} type="button" className="btn secondary small" disabled={busy} aria-label={`Remove ${o.user.full_name}`}
                onClick={() => setRemoving(o)}>
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
      {requirement.owners.length === 0 && <p className="muted" style={{ margin: 0 }}>No placement officer owner or collaborators yet.</p>}
      {removing && (
        <BdmConfirm label="Confirm removal" confirmText="Yes, remove" busyText="Removing…" busy={busy} onConfirm={() => remove(removing)}
          onCancel={() => { const target = removeId(removing); setRemoving(null); focus(target); }}>
          Remove {removing.user.full_name} ({removing.role_label}) from {requirement.code}?
        </BdmConfirm>
      )}
      {manage && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <label style={{ display: "grid", gap: 4 }}>
            Owner role
            <select value={role} onChange={(e) => { setRole(e.target.value as OwnerRole); setPicked(null); }}>
              {OWNER_ROLE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          <div style={{ flex: "1 1 240px" }}>
            <SearchableSelect key={`${role}-${requirement.owners.length}`} label="Person" noun="employee" search={search} onChange={setPicked} />
          </div>
          <button type="button" className="btn secondary small" disabled={!picked || busy} onClick={add}>
            {busy && !removing ? "Adding…" : "Add owner"}
          </button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </section>
  );
}

const HISTORY_PAGE = 20;

/** hrc-006 (AC3): every add, remove and primary change, newest first, 20 at a time. The page re-keys it when the owners change. */
export function OwnershipHistory({ requirementId }: { requirementId: string }) {
  const [items, setItems] = useState<OwnerChange[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const headingId = `${useId()}-ownership`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailed(false);
    const query = new URLSearchParams({ limit: String(HISTORY_PAGE), offset: String(offset) });
    fetch(`${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/assignment-history?${query}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: OwnerChangePage) => {
        if (!Array.isArray(body?.items)) throw new Error("shape");
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
  }, [requirementId, offset, retry]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Ownership history</h3>
      {items.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {items.map((c) => (
            <li key={c.id}>
              <LocalTime value={c.created_at} time />: {ownerChangeText(c)}
            </li>
          ))}
        </ul>
      )}
      {loading ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading ownership history…</p>
      ) : failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the ownership history.</p>
          <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </div>
      ) : items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No ownership changes recorded yet.</p>
      ) : items.length < total && (
        <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setOffset(items.length)}>
          Show more
        </button>
      )}
    </section>
  );
}
