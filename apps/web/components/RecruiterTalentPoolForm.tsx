"use client";

import { type FormEvent, useState } from "react";

import { SkillChips } from "@/components/RecruiterFindCandidates";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { distinctTerms, GROUP_TERMS, MAX_GROUPS, MAX_TERMS, unknownSkill } from "@/lib/recruiterCandidateSearch";
import { isPool, type Pool, poolBody, type PoolForm, POOLS_URL, poolUrl, yearsProblem } from "@/lib/recruiterPools";

const termCount = (f: PoolForm) => f.all.length + f.any.reduce((n, g) => n + g.length, 0);

/** rec-015 (P4/P7): create or edit a pool -- its name, the rec-013 skill chips (all of / at least one of) and an experience band in whole
 *  years. Save adds any skill typed but not yet added. The API checks every skill against the Skills Master (a 422 names suggestions). */
export default function RecruiterTalentPoolForm({ initial, poolId, onSaved, onCancel }: {
  initial: PoolForm; poolId?: string; onSaved: (pool: Pool) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState<PoolForm>(initial);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const set = <K extends keyof PoolForm>(field: K, value: PoolForm[K]) => setForm((f) => ({ ...f, [field]: value }));
  const room = termCount(form) < MAX_TERMS;
  const prefix = poolId ? "pool-edit" : "pool-new";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const next = {
      ...form,
      all: distinctTerms([...form.all, texts.all ?? ""], MAX_TERMS),
      any: form.any.map((g, i) => distinctTerms([...g, texts[`any${i}`] ?? ""], GROUP_TERMS)),
    };
    setForm(next);
    setTexts({});
    const problem = !next.name.trim() ? "Enter a pool name." : yearsProblem(next);
    if (problem) return setFailure(problem);
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(poolId ? poolUrl(poolId) : POOLS_URL, poolId ? "PATCH" : "POST", poolBody(next, !!poolId));
    setBusy(false);
    if (outcome.ok && isPool(outcome.data)) return onSaved(outcome.data);
    if (outcome.ok) return setFailure("The pool could not be saved. Try again.");
    // an unknown skill's 422 is an object whose message already names the suggestions (rec-013 FS3)
    const message = unknownSkill(outcome.detail) ? String((outcome.detail as { message?: unknown }).message ?? "") : detailMessage(outcome.detail, outcome.message);
    setFailure(message || outcome.message);
  }

  return (
    <form onSubmit={submit} className="action-card" style={{ gap: 14 }} aria-label={poolId ? "Edit talent pool" : "New talent pool"} noValidate>
      <h3 style={{ margin: 0 }}>{poolId ? "Edit pool" : "New talent pool"}</h3>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={`${prefix}-name`}>Pool name</label>
        <input id={`${prefix}-name`} maxLength={80} required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Cloud Engineers" />
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        Candidates join automatically when their skills and experience match. Use skills, an experience range, or both.
      </p>
      <SkillChips id={`${prefix}-all`} label="Must have all of these skills" hint="Type a skill or another name for it, then press Enter. Related skills count too."
        terms={form.all} text={texts.all ?? ""} room={room} onText={(v) => setTexts((t) => ({ ...t, all: v }))} onChange={(all) => set("all", all)} />
      {form.any.map((group, i) => (
        <div key={i} style={{ borderLeft: "3px solid var(--line)", paddingLeft: 10, display: "grid", gap: 6 }}>
          <SkillChips id={`${prefix}-any${i}`} label={`And at least one of these (group ${i + 1})`} hint="A candidate needs any one of these skills."
            terms={group} text={texts[`any${i}`] ?? ""} room={room && group.length < GROUP_TERMS}
            onText={(v) => setTexts((t) => ({ ...t, [`any${i}`]: v }))}
            onChange={(terms) => set("any", form.any.map((g, n) => (n === i ? terms : g)))} />
          <button type="button" className="btn ghost small" style={{ justifySelf: "start" }}
            onClick={() => { set("any", form.any.filter((_, n) => n !== i)); setTexts({}); }}>Remove group {i + 1}</button>
        </div>
      ))}
      {form.any.length < MAX_GROUPS && (
        <button type="button" className="btn ghost small" style={{ justifySelf: "start" }} onClick={() => set("any", [...form.any, []])}>
          + Add an “at least one of” group
        </button>
      )}
      {!room && <p className="muted" role="status" style={{ margin: 0 }}>A pool can use up to {MAX_TERMS} skills.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: 12 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${prefix}-exp-min`}>Experience from (years)</label>
          <input id={`${prefix}-exp-min`} type="number" inputMode="numeric" min={0} max={50} value={form.expMin} onChange={(e) => set("expMin", e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${prefix}-exp-max`}>Experience to (years)</label>
          <input id={`${prefix}-exp-max`} type="number" inputMode="numeric" min={0} max={50} aria-describedby={`${prefix}-exp-hint`}
            value={form.expMax} onChange={(e) => set("expMax", e.target.value)} />
          <span id={`${prefix}-exp-hint`} className="muted" style={{ fontSize: 13 }}>&quot;0&quot; means under 1 year (freshers).</span>
        </div>
      </div>
      {poolId && (
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} /> Active (recruiters can see this pool)
        </label>
      )}
      {failure && (
        <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>
      )}
      <div className="actions" style={{ gap: 8 }}>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : poolId ? "Save changes" : "Create pool"}</button>
        <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
