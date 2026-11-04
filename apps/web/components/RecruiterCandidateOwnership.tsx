"use client";

import { type KeyboardEvent, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { assigneeSearch, candidateUrl, personLabel, type CandidateDetail, type CandidateOwnership, type OwnerRef } from "@/lib/recruiterCandidates";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const pick = (p: OwnerRef): PickOption => ({ id: p.id, label: p.full_name });

// hrc-012 (DEC-SCOPE-381): the candidate's owners -- one primary recruiter (O2), a placement officer (O3) and collaborators (O4, shown
// while shared ownership is on or some remain). Change ownership is offered to the primary recruiter and managers (`can_assign`); the API
// re-checks every rule. Only changed keys are sent. The RecruiterReassign conventions: no dialog library, the group takes focus, Escape
// cancels, an error takes focus.
export default function RecruiterCandidateOwnership({ candidateId, ownership, onSaved }: {
  candidateId: string; ownership: CandidateOwnership; onSaved: (detail: CandidateDetail) => void;
}) {
  const [open, setOpen] = useState(false);
  const [owner, setOwner] = useState<PickOption | null>(null);
  const [officer, setOfficer] = useState<PickOption | null>(null);
  const [collaborators, setCollaborators] = useState<PickOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `cand-own-${name}`;
  const showCollaborators = ownership.shared_ownership || ownership.collaborators.length > 0;

  function start() {
    setOwner(ownership.owner && pick(ownership.owner));
    setOfficer(ownership.placement_officer && pick(ownership.placement_officer));
    setCollaborators(ownership.collaborators.map(pick));
    setNotice(null);
    setError(null);
    setOpen(true);
    focus(id("group"));
  }

  function close() {
    setOpen(false);
    setError(null);
    focus(id("open"));
  }

  function body(): Record<string, unknown> {
    const sent: Record<string, unknown> = {};
    if (owner && owner.id !== ownership.owner?.id) sent.owner_user_id = owner.id;
    if ((officer?.id ?? null) !== (ownership.placement_officer?.id ?? null)) sent.placement_officer_user_id = officer?.id ?? null;
    const ids = collaborators.map((c) => c.id);
    if (ids.join() !== ownership.collaborators.map((c) => c.id).join()) sent.collaborator_user_ids = ids;
    return sent;
  }

  async function save() {
    if (busy) return;
    const sent = body();
    if (Object.keys(sent).length === 0) return close();
    setBusy(true);
    setError(null);
    const outcome = await sendJson(candidateUrl(candidateId, "/ownership"), "PUT", sent);
    setBusy(false);
    if (!outcome.ok) {
      setError((outcome.status ?? 0) >= 500 ? "We couldn't change who owns this candidate. Please try again." : outcome.message);
      focus(id("error"));
      return;
    }
    onSaved(outcome.data as unknown as CandidateDetail);
    setNotice("Ownership updated.");
    close();
  }

  const rows: [string, string][] = [
    ["Primary recruiter", personLabel(ownership.owner)],
    ["Placement officer", personLabel(ownership.placement_officer, "—")],
    ...(showCollaborators ? [["Collaborators", ownership.collaborators.map((c) => personLabel(c)).join(", ") || "None"] as [string, string]] : []),
  ];

  return (
    <section aria-labelledby="cand-ownership-heading" className="action-card">
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <h3 id="cand-ownership-heading" style={{ margin: 0 }}>Ownership</h3>
        {ownership.can_assign && !open && <button id={id("open")} type="button" className="btn secondary small" onClick={start}>Change ownership</button>}
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "8px 16px", margin: "12px 0 0" }}>
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {notice && <p role="status" className="form-message" style={{ margin: "8px 0 0" }}>{notice}</p>}
      {open && (
        <div id={id("group")} tabIndex={-1} role="group" aria-label="Change ownership" className="form" style={{ marginTop: 12 }}
          onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") close(); }}>
          <SearchableSelect id={id("owner")} label="Primary recruiter" noun="recruiter" search={assigneeSearch("recruiter")} initial={owner} disabled={busy}
            onChange={(o) => o && setOwner(o)} />
          {officer ? (
            <div className="field">
              <span className="muted" style={{ fontSize: 13 }}>Placement officer</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <span>{officer.label}</span>
                <button type="button" className="btn secondary small" onClick={() => setOfficer(null)} disabled={busy}>Remove placement officer</button>
              </div>
            </div>
          ) : (
            <SearchableSelect id={id("officer")} label="Placement officer" noun="employee" search={assigneeSearch("officer")} disabled={busy} onChange={setOfficer} />
          )}
          {showCollaborators && (
            <div className="field">
              <span className="muted" style={{ fontSize: 13 }}>Collaborators</span>
              {collaborators.length === 0 ? <p className="muted" style={{ margin: 0 }}>None</p> : (
                <ul style={{ display: "flex", flexWrap: "wrap", gap: 8, listStyle: "none", padding: 0, margin: 0 }}>
                  {collaborators.map((c) => (
                    <li key={c.id} className="badge" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      {c.label}
                      <button type="button" className="btn secondary small" aria-label={`Remove ${c.label}`} disabled={busy}
                        onClick={() => setCollaborators((list) => list.filter((x) => x.id !== c.id))}>×</button>
                    </li>
                  ))}
                </ul>
              )}
              {ownership.shared_ownership && (
                <SearchableSelect key={collaborators.length} id={id("collab")} label="Add a collaborator" noun="employee" disabled={busy}
                  search={assigneeSearch("collaborator", [...collaborators.map((c) => c.id), ...(owner ? [owner.id] : [])])}
                  onChange={(o) => o && setCollaborators((list) => (list.some((x) => x.id === o.id) ? list : [...list, o]))} />
              )}
            </div>
          )}
          <div className="actions">
            <button type="button" className="btn small" disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save ownership"}</button>
            <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
          </div>
          {error && <p id={id("error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
