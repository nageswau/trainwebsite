"use client";
import Link from "next/link";
import { type FormEvent, useEffect, useId, useState } from "react";

import RecruiterShareDialog, { type ShareCandidate } from "@/components/RecruiterShareDialog";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { isApplicationBody, requirementCandidatesUrl } from "@/lib/recruiterApplications";
import { CANDIDATES_PATH, experienceLabel } from "@/lib/recruiterCandidates";
import { type CriteriaSkill, isMatches, MATCH_PAGE_SIZE, type Matches, type MatchRow, matchesUrl, WEIGHT_MAX, WEIGHT_MIN, weightsUrl } from "@/lib/recruiterMatching";
import { isRequirementBody, type Requirement } from "@/lib/recruiterRequirements";
import { UNSHAREABLE } from "@/lib/recruiterShares";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Notice = { text: string; failed: boolean } | null;
const WEIGHT_ERROR = `Each weight must be a whole number from ${WEIGHT_MIN} to ${WEIGHT_MAX}.`;
/** M1: one number per requirement skill; the API re-checks every rule (ids, range, who may edit). */
function WeightsForm({ requirementId, skills, onSaved, onCancel }: {
  requirementId: string; skills: CriteriaSkill[]; onSaved: (r: Requirement) => void; onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(skills.map((s) => [s.id, String(s.weight)])));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const weights = skills.map((s) => ({ id: s.id, weight: Number(values[s.id]) }));
    if (weights.some((w) => !Number.isInteger(w.weight) || w.weight < WEIGHT_MIN || w.weight > WEIGHT_MAX)) return setFailure(WEIGHT_ERROR);
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(weightsUrl(requirementId), "PUT", { weights });
    setBusy(false);
    if (outcome.ok && isRequirementBody(outcome.data)) onSaved(outcome.data.requirement);
    else setFailure(outcome.ok ? "Unable to save the weights." : outcome.message);
  }

  return (
    <form onSubmit={submit} className="action-card" style={{ gap: 10 }} aria-label="Match weights" noValidate>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        A higher weight makes a skill count for more of the score ({WEIGHT_MIN} = least, {WEIGHT_MAX} = most).
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: 10 }}>
        {skills.map((s) => (
          <div key={s.id} className="field" style={{ marginBottom: 0 }}>
            <label htmlFor={`${id}-${s.id}`}>Weight of {s.name} ({s.kind})</label>
            <input id={`${id}-${s.id}`} type="number" inputMode="numeric" min={WEIGHT_MIN} max={WEIGHT_MAX} step={1} value={values[s.id]}
              onChange={(e) => setValues((v) => ({ ...v, [s.id]: e.target.value }))} />
          </div>
        ))}
      </div>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save weights"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function criteriaText(m: Matches): string {
  const parts = m.criteria.skills.filter((s) => s.in_master).map((s) => `${s.name} ${s.points}`);
  if (m.criteria.experience) parts.push(`Experience ${m.criteria.experience.points}`);
  if (m.criteria.location) parts.push(`Location (${m.criteria.location.value}) ${m.criteria.location.points}`);
  return parts.join(" · ");
}

function MatchItem({ m, writes, canShortlist, busy, selected, onSelect, onShortlist }: {
  m: MatchRow; writes: boolean; canShortlist: boolean; busy: boolean; selected: boolean | null; onSelect: (on: boolean) => void; onShortlist: () => void;
}) {
  const id = useId();
  const facts = [m.preferred_role, m.experience_months === null ? null : experienceLabel(m.experience_months), m.location].filter(Boolean).join(" | ");
  const profile = `${CANDIDATES_PATH}/${encodeURIComponent(m.id)}`;
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-name`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        {selected !== null && <input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} aria-label={`Select ${m.name} to share`} />}
        <Link id={`${id}-name`} href={profile} style={{ ...LINK_STYLE, fontWeight: 600, overflowWrap: "anywhere" }}>{m.name}</Link>
        <span className="badge">{m.score}% match</span>
        {m.application ? <span className="badge">{m.application.status_label}</span> : <span className="muted" style={{ fontSize: 13 }}>Not on this requirement</span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>{[m.candidate_code, facts].filter(Boolean).join(" · ")}</p>
      <ul aria-label={`Score breakdown for ${m.name}`} style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 6 }}>
        {m.breakdown.map((b) => (
          <li key={b.key} className={b.matched ? "badge" : undefined}
            style={b.matched ? undefined : { border: "1px solid var(--line)", borderRadius: 99, padding: "4px 10px", fontSize: 12 }}>
            {b.label}: {b.points} of {b.max}<span className="visually-hidden"> ({b.matched ? "matched" : "missing"})</span>
          </li>
        ))}
      </ul>
      <div className="actions" style={{ flexWrap: "wrap", gap: 8 }}>
        <Link className="btn secondary small" href={profile} aria-label={`View profile of ${m.name}`}>View profile</Link>
        {writes && <Link className="btn secondary small" href={`${profile}#contact`} aria-label={`Contact ${m.name}`}>Contact</Link>}
        {canShortlist && !m.application && (
          <button type="button" className="btn small" disabled={busy} aria-label={`Shortlist ${m.name}`} onClick={onShortlist}>
            {busy ? "Shortlisting…" : "Shortlist"}
          </button>
        )}
      </div>
    </li>
  );
}

/** rec-016 (DEC-SCOPE-157): the requirement's matching candidates, ranked by the weighted score with each row's breakdown and its status on
 *  this requirement. Shortlist is rec-017's add at Shortlisted (one per candidate); writers adjust the skill weights. `version` (the
 *  requirement's updated_at) re-reads the ranking after the requirement's skills change. rec-019: writers select rows (kept across pages)
 *  and share them with the company. */
export default function RecruiterRequirementMatches({ requirementId, requirementLabel = "this requirement", companyId, version, onShortlisted, onShared, onRequirementChanged }: {
  requirementId: string; requirementLabel?: string; companyId?: string; version?: string; onShortlisted?: () => void; onShared?: () => void;
  onRequirementChanged?: (r: Requirement) => void;
}) {
  const [data, setData] = useState<Matches | null>(null);
  const [failed, setFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [reloads, setReloads] = useState(0);
  const [editing, setEditing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [selected, setSelected] = useState<Map<string, ShareCandidate>>(new Map());
  const [sharing, setSharing] = useState<ShareCandidate[] | null>(null); // the selection when the dialog opened (QA-01)
  const headingId = `${useId()}-matches`;
  const adjustId = `${headingId}-adjust`;
  const focus = useFocusAfterRender();
  const reload = () => setReloads((n) => n + 1);
  const closeWeights = () => {
    setEditing(false);
    focus(adjustId); // QA-02: back to the button that opened the form
  };

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(matchesUrl(requirementId, offset), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isMatches(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requirementId, offset, version, reloads]);

  async function shortlist(m: MatchRow) {
    setBusyId(m.id);
    setNotice(null);
    const outcome = await sendJson(requirementCandidatesUrl(requirementId), "POST", { candidate_id: m.id, status: "shortlisted" });
    setBusyId(null);
    if (outcome.ok && isApplicationBody(outcome.data)) {
      const a = outcome.data.application;
      setData((d) => d && { ...d, items: d.items.map((x) => (x.id === m.id ? { ...x, application: { id: a.id, status: a.status, status_label: a.status_label } } : x)) });
      setNotice({ text: `${m.name} shortlisted.`, failed: false });
      onShortlisted?.();
    } else setNotice({ text: outcome.ok ? "Unable to shortlist the candidate." : outcome.message, failed: true });
  }

  const shareable = (m: MatchRow) => !!data?.can_shortlist && !UNSHAREABLE.includes(m.application?.status ?? "");
  const select = (m: MatchRow, on: boolean) => setSelected((current) => {
    const next = new Map(current);
    if (on) next.set(m.id, { id: m.id, name: m.name, code: m.candidate_code });
    else next.delete(m.id);
    return next;
  });
  const writes = !!data && (data.can_shortlist || data.can_edit_weights);
  const unused = data?.criteria.skills.filter((s) => !s.in_master) ?? [];
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={headingId} style={{ margin: 0 }}>Matching candidates{data && !data.reason ? ` (${data.total})` : ""}</h3>
        <div className="actions" style={{ flexWrap: "wrap", gap: 8 }}>
          {selected.size > 0 && !sharing && (
            <button type="button" className="btn small" onClick={() => { setSharing([...selected.values()]); setNotice(null); }}>Share selected ({selected.size})</button>
          )}
          {data?.can_edit_weights && data.criteria.skills.length > 0 && !editing && (
            <button id={adjustId} type="button" className="btn secondary small" onClick={() => { setEditing(true); setNotice(null); }}>Adjust weights</button>
          )}
        </div>
      </div>
      {data && !data.reason && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Score out of 100: {criteriaText(data)}. Candidates must have every required skill.</p>
      )}
      {unused.length > 0 && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Not used for matching (not in the Skills Master): {unused.map((s) => s.name).join(", ")}
        </p>
      )}
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {sharing && (
        <RecruiterShareDialog requirement={{ id: requirementId, label: requirementLabel }} companyId={companyId} candidates={sharing}
          onClose={() => setSharing(null)} onShared={() => { setSelected(new Map()); reload(); onShared?.(); }} />
      )}
      {editing && data && (
        <WeightsForm requirementId={requirementId} skills={data.criteria.skills} onCancel={closeWeights}
          onSaved={(r) => { closeWeights(); setNotice({ text: "Match weights saved.", failed: false }); onRequirementChanged?.(r); reload(); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load matching candidates.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading matching candidates…</p>
      ) : data.reason === "no_skills" ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>
          Add required or preferred skills from the Skills Master to this requirement to see matching candidates.
        </p>
      ) : data.items.length === 0 && data.total === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No candidates in the pool have the required skills yet.</p>
      ) : (
        <>
          <ul aria-label="Matching candidates" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((m) => (
              <MatchItem key={m.id} m={m} writes={writes} canShortlist={data.can_shortlist} busy={busyId === m.id} onShortlist={() => void shortlist(m)}
                selected={shareable(m) ? selected.has(m.id) : null} onSelect={(on) => select(m, on)} />
            ))}
          </ul>
          {data.total > MATCH_PAGE_SIZE && (
            <nav aria-label="Matching candidate pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - MATCH_PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(data.offset + MATCH_PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
