"use client";
import { type FormEvent, useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { isRequirementBody, type Requirement, REQUIREMENTS_URL, VISIBILITY_HINT, VISIBILITY_OPTIONS, type Visibility } from "@/lib/recruiterRequirements";

// hrc-008 (DEC-SCOPE-383 V1/V4/V7): who sees this job. Every reader sees the current choice; a `jobs.publish` holder (`can_change`) gets
// the form. The server validates the pool and the grant; this only sends and shows its answer.
type Pool = { id: string; name: string };
const POOLS_URL = "/api/v1/recruiter/pools"; // rec-015: active pools only, by name

export default function RequirementVisibility({ requirement, onDone }: { requirement: Requirement; onDone: (r: Requirement, notice: string) => void }) {
  const current = requirement.visibility;
  const [choice, setChoice] = useState<Visibility>(current.key);
  const [poolId, setPoolId] = useState(current.segment_pool?.id ?? "");
  const [pools, setPools] = useState<Pool[] | null>(null);
  const [poolsFailed, setPoolsFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `requirement-${requirement.id}-visibility`;

  useEffect(() => {
    if (!current.can_change || choice !== "segment" || pools) return;
    let live = true;
    fetch(POOLS_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: { items?: Pool[] }) => live && setPools(body.items ?? []))
      .catch(() => live && setPoolsFailed(true));
    return () => {
      live = false;
    };
  }, [current.can_change, choice, pools]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (choice === "segment" && !poolId) {
      setFailure("Choose the talent pool that may see this job.");
      document.getElementById(`${id}-pool`)?.focus();
      return;
    }
    setBusy(true);
    setFailure(null);
    const body = choice === "segment" ? { visibility: choice, segment_pool_id: poolId } : { visibility: choice };
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${encodeURIComponent(requirement.id)}/visibility`, "PUT", body);
    setBusy(false);
    if (outcome.ok && isRequirementBody(outcome.data)) onDone(outcome.data.requirement, `Visibility saved: ${outcome.data.requirement.visibility.label}.`);
    else setFailure(outcome.ok ? "Unable to save the visibility." : outcome.message);
  }

  const summary = current.key === "segment" && current.segment_pool ? `${current.label}: ${current.segment_pool.name}` : current.label;
  const unchanged = choice === current.key && (choice !== "segment" || poolId === (current.segment_pool?.id ?? ""));
  return (
    <section className="action-card wide" aria-labelledby={id}>
      <h3 id={id}>Visibility</h3>
      <p style={{ margin: 0 }}>
        <strong>{summary}</strong>
        {!current.can_change && <> — {VISIBILITY_HINT[current.key]}</>}
      </p>
      {current.can_change && (
        <form className="form" onSubmit={save} aria-busy={busy}>
          <div className="field">
            <label htmlFor={`${id}-choice`}>Who can see this job</label>
            <select id={`${id}-choice`} value={choice} aria-describedby={`${id}-hint`} onChange={(e) => { setChoice(e.target.value as Visibility); setFailure(null); }}>
              {VISIBILITY_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
            <span id={`${id}-hint`} className="muted">{VISIBILITY_HINT[choice]}</span>
          </div>
          {choice === "segment" && (
            <div className="field">
              <label htmlFor={`${id}-pool`}>Talent pool</label>
              <select id={`${id}-pool`} value={poolId} disabled={!pools} aria-invalid={failure && !poolId ? true : undefined}
                aria-describedby={failure ? `${id}-error` : undefined} onChange={(e) => { setPoolId(e.target.value); setFailure(null); }}>
                <option value="">{pools ? "Choose a talent pool" : poolsFailed ? "Talent pools could not be loaded" : "Loading talent pools…"}</option>
                {pools?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {pools && pools.length === 0 && <span className="muted">There are no active talent pools yet.</span>}
            </div>
          )}
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy || unchanged}>
              {busy ? "Saving…" : "Save visibility"}
            </button>
          </div>
        </form>
      )}
      {failure && (
        <p id={`${id}-error`} className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}
