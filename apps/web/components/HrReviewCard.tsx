"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { CHECKLIST_ITEMS, type ChecklistKey, formatDay, HR_SETTABLE_STAGES, hrTaskUrl, STAGE_LABELS, type HrReviewStage, type HrReviewTask } from "@/lib/hrReviews";

type Draft = { stage: HrReviewStage; screening_date: string; role_preferences: string; skill_gap_notes: string; checklist: ChecklistKey[] };
type Load = { kind: "loading" } | { kind: "none" } | { kind: "failed" } | { kind: "ready"; task: HrReviewTask };

const toDraft = (t: HrReviewTask): Draft => ({
  stage: t.stage, screening_date: t.screening_date ?? "", role_preferences: t.role_preferences ?? "", skill_gap_notes: t.skill_gap_notes ?? "", checklist: t.checklist,
});

// itc-027 (DEC-SCOPE-354): the HR owner's review of one student, on the HR student page -- stage, screening date, role preferences,
// the checklist and the internal skill-gap notes, saved together. The API answers 404 to anyone but the owner, so the card then says
// the review is someone else's. A closed review is read-only until a new shared resume version re-opens it.
export default function HrReviewCard({ studentId }: { studentId: string }) {
  const id = useId();
  const sending = useRef(false);
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);

  const fetchTask = useCallback(async () => {
    setLoad({ kind: "loading" });
    try {
      const response = await fetch(hrTaskUrl(studentId), { cache: "no-store" });
      if (response.status === 404) return setLoad({ kind: "none" });
      if (!response.ok) throw new Error(String(response.status));
      const task: HrReviewTask = await response.json();
      setLoad({ kind: "ready", task });
      setDraft(toDraft(task));
    } catch {
      setLoad({ kind: "failed" });
    }
  }, [studentId]);

  useEffect(() => { void fetchTask(); }, [fetchTask]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft || sending.current) return;
    sending.current = true;
    setBusy(true);
    setNotice(null);
    const outcome = await sendJson(hrTaskUrl(studentId), "PATCH", { ...draft, screening_date: draft.screening_date || null });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message || "The review could not be saved.", failed: true });
    const task = outcome.data as HrReviewTask;
    setLoad({ kind: "ready", task });
    setDraft(toDraft(task));
    setNotice({ text: "Review saved.", failed: false });
  }

  const toggle = (key: ChecklistKey, on: boolean) =>
    draft && setDraft({ ...draft, checklist: on ? [...draft.checklist, key] : draft.checklist.filter((k) => k !== key) });

  return (
    <section aria-labelledby={`${id}-title`} className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id={`${id}-title`} style={{ margin: 0 }}>Resume review</h3>
      {load.kind === "loading" && <p className="muted" role="status" style={{ margin: 0 }}>Loading the review…</p>}
      {load.kind === "failed" && (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          The review could not be loaded. <button type="button" className="btn secondary small" onClick={() => void fetchTask()}>Try again</button>
        </p>
      )}
      {load.kind === "none" && <p className="muted" style={{ margin: 0 }}>No resume review of this student is assigned to you. The IT Admin assigns reviews; see your Review Queue.</p>}
      {load.kind === "ready" && draft && (
        <>
          <p className="muted" style={{ margin: 0 }}>
            <span className="badge">{load.task.stage_label}</span> Resume version {load.task.resume_version} · assigned <LocalTime value={load.task.assigned_at ?? load.task.updated_at} />
          </p>
          {load.task.closed_at ? (
            <p style={{ margin: 0 }}>This review is closed ({STAGE_LABELS[load.task.stage].toLowerCase()}). A new resume version shared with HR re-opens it.</p>
          ) : (
            <form onSubmit={save} style={{ display: "grid", gap: 12 }}>
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(min(14rem, 100%), 1fr))" }}>
                <div className="field" style={{ margin: 0 }}>
                  <label htmlFor={`${id}-stage`}>Stage</label>
                  <select id={`${id}-stage`} value={draft.stage} disabled={busy} onChange={(e) => setDraft({ ...draft, stage: e.target.value as HrReviewStage })}>
                    {HR_SETTABLE_STAGES.map((s) => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
                  </select>
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <label htmlFor={`${id}-date`}>Screening date</label>
                  <input id={`${id}-date`} type="date" value={draft.screening_date} disabled={busy} onChange={(e) => setDraft({ ...draft, screening_date: e.target.value })} />
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <label htmlFor={`${id}-roles`}>Role preferences</label>
                  <input id={`${id}-roles`} type="text" maxLength={300} value={draft.role_preferences} disabled={busy} onChange={(e) => setDraft({ ...draft, role_preferences: e.target.value })} />
                </div>
              </div>
              <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
                <legend style={{ fontWeight: 600, marginBottom: 6 }}>Review checklist</legend>
                {CHECKLIST_ITEMS.map((item) => (
                  <label key={item.key} style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                    <input type="checkbox" checked={draft.checklist.includes(item.key)} disabled={busy} onChange={(e) => toggle(item.key, e.target.checked)} /> {item.label}
                  </label>
                ))}
              </fieldset>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor={`${id}-notes`}>Skill-gap notes (internal: never shown to the student or counselor)</label>
                <textarea id={`${id}-notes`} rows={4} maxLength={4000} value={draft.skill_gap_notes} disabled={busy} onChange={(e) => setDraft({ ...draft, skill_gap_notes: e.target.value })} />
              </div>
              <div className="actions">
                <button type="submit" className="btn small" disabled={busy} aria-busy={busy}>{busy ? "Saving…" : "Save review"}</button>
                <Link className="btn small secondary" href="/it/hr/interviews">Interviews</Link>
                <Link className="btn small secondary" href="/it/hr/shortlists">Shortlists</Link>
              </div>
            </form>
          )}
          {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
          <details>
            <summary>Stage history ({load.task.history.length})</summary>
            <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
              {load.task.history.map((h, i) => (
                <li key={`${h.created_at}-${i}`}>
                  {formatDay(h.created_at)}: {STAGE_LABELS[h.to_stage]}{h.actor ? ` by ${h.actor}` : h.reason === "upload" ? " (resume shared)" : h.reason === "withdrawn" ? " (left placement)" : ""}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
