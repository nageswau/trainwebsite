"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { CANDIDATES_PATH, STATUS_LABEL } from "@/lib/recruiterCandidates";
import { MERGE_FIELD_LABEL, MOVED_LABEL, isMergePreview, mergePath, mergeUrl, type MergeField, type MergePreview } from "@/lib/recruiterDuplicates";

// hrc-014 (DEC-SCOPE-377 D4-D8): merge the duplicate (`victimCode`) into the candidate that stays (`survivorId`), side by side. Where both
// have a different value the user picks one; an empty value here is always filled from the duplicate. Mobile, email and salary are shown
// but stay where they are. "Keep … instead" swaps the direction. An open application on a requirement both are on blocks the merge.
const empty = (value: unknown) => value === null || value === undefined || value === "";
const shown = (value: unknown) => (empty(value) ? <span className="muted">—</span> : String(value));
const FIXED: [string, string][] = [["mobile", "Mobile"], ["email", "Email"], ["expected_salary", "Expected salary"]];

export default function RecruiterCandidateMerge({ survivorId, victimCode }: { survivorId: string; victimCode: string }) {
  const router = useRouter();
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [loadError, setLoadError] = useState("");
  const [useVictim, setUseVictim] = useState<MergeField[]>([]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const id = useId();

  useEffect(() => {
    let live = true;
    void sendRequest(mergeUrl(survivorId, victimCode), { method: "GET" }).then((outcome) => {
      if (!live) return;
      if (outcome.ok && isMergePreview(outcome.data)) setPreview(outcome.data);
      else setLoadError(outcome.ok ? "Unable to compare the candidates." : outcome.message);
    });
    return () => { live = false; };
  }, [survivorId, victimCode]);

  if (loadError) return <div className="action-card"><p className="form-error" role="alert" style={{ margin: 0 }}>{loadError}</p></div>;
  if (!preview) return <p className="muted" role="status">Loading the comparison…</p>;

  const { survivor, victim } = preview;
  const mine = `Stays (${survivor.candidate_code})`;
  const theirs = `Merges in (${victim.candidate_code})`;
  const blocking = preview.conflicts.filter((c) => c.blocking);
  const kept = preview.conflicts.filter((c) => !c.blocking);
  const moved = MOVED_LABEL.filter(([key]) => preview.moved[key] > 0).map(([key, label]) => `${label}: ${preview.moved[key]}`);
  const pick = (field: MergeField, fromVictim: boolean) =>
    setUseVictim((fields) => (fromVictim ? [...fields.filter((f) => f !== field), field] : fields.filter((f) => f !== field)));

  async function merge() {
    if (sending.current) return;
    if (!window.confirm(`Merge ${victim.candidate_code} into ${survivor.candidate_code}? ${victim.candidate_code} is archived for good and cannot be restored.`)) return;
    sending.current = true;
    setBusy(true);
    setError("");
    const text = reason.trim();
    const outcome = await sendJson(mergeUrl(survivor.id), "POST", { victim_code: victim.candidate_code, use_victim: useVictim, ...(text ? { reason: text } : {}) });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    router.push(`${CANDIDATES_PATH}/${encodeURIComponent(survivor.id)}?${new URLSearchParams({ merged: victim.candidate_code })}`);
  }

  return (
    <section aria-labelledby={`${id}-heading`} style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Duplicate review</div>
          <h2 id={`${id}-heading`}>Merge {victim.candidate_code} into {survivor.candidate_code}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {survivor.candidate_code} stays. Requirements, profile shares, calls, messages, skills, resumes and documents of {victim.candidate_code} move to it, and{" "}
            {victim.candidate_code} is archived as merged. Mobile, email and salary stay on each record.
          </p>
        </div>
        <Link className="btn secondary small" style={{ whiteSpace: "nowrap" }} href={mergePath(victim.id, survivor.candidate_code)}>Keep {victim.candidate_code} instead</Link>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="table compact stack">
          <caption style={{ textAlign: "left", fontWeight: 600 }}>Compare the two candidates</caption>
          <thead>
            <tr><th scope="col">Field</th><th scope="col">{mine}</th><th scope="col">{theirs}</th></tr>
          </thead>
          <tbody>
            {preview.fields.map((key) => {
              const label = MERGE_FIELD_LABEL[key] ?? key;
              const a = survivor[key];
              const b = victim[key];
              const choice = !empty(a) && !empty(b) && String(a) !== String(b);
              const fromVictim = useVictim.includes(key);
              const cell = (value: unknown, isVictim: boolean) => choice ? (
                <label style={{ display: "flex", gap: 6, alignItems: "baseline", overflowWrap: "anywhere" }}>
                  <input type="radio" name={`${id}-${key}`} checked={fromVictim === isVictim} disabled={busy}
                    aria-label={`Keep ${String(value)} for ${label}`} onChange={() => pick(key, isVictim)} />
                  {String(value)}
                </label>
              ) : <span style={{ overflowWrap: "anywhere" }}>{shown(value)}</span>;
              return (
                <tr key={key}>
                  <th scope="row">{label}</th>
                  <td data-label={mine}>{cell(a, false)}{!choice && empty(a) && !empty(b) && <span className="muted" style={{ fontSize: 12 }}> (filled from the duplicate)</span>}</td>
                  <td data-label={theirs}>{cell(b, true)}</td>
                </tr>
              );
            })}
            {FIXED.filter(([key]) => key in survivor || key in victim).map(([key, label]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td data-label={mine}><span style={{ overflowWrap: "anywhere" }}>{shown(survivor[key as keyof typeof survivor])}</span></td>
                <td data-label={theirs}><span style={{ overflowWrap: "anywhere" }}>{shown(victim[key as keyof typeof victim])}</span> <span className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>(stays)</span></td>
              </tr>
            ))}
            <tr>
              <th scope="row">Status</th>
              <td data-label={mine}>{STATUS_LABEL[survivor.status] ?? survivor.status}</td>
              <td data-label={theirs}>{STATUS_LABEL[victim.status] ?? victim.status} → Archived (merged)</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p style={{ margin: 0 }}>{moved.length ? `Moves to ${survivor.candidate_code}: ${moved.join(", ")}.` : `${victim.candidate_code} has no records to move.`}</p>
      {kept.length > 0 && (
        <p className="muted" style={{ margin: 0 }}>
          Both are on {kept.map((c) => c.job_title).join(", ")}; {victim.candidate_code}&apos;s closed application there stays on the archived record.
        </p>
      )}
      {blocking.length > 0 && (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          Both are on {blocking.map((c) => c.job_title).join(", ")}. Reject or withdraw {victim.candidate_code}&apos;s application there before merging.
        </p>
      )}
      <div className="field" style={{ margin: 0, maxWidth: 640 }}>
        <label htmlFor={`${id}-reason`}>Reason (optional)</label>
        <textarea id={`${id}-reason`} rows={2} maxLength={500} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-live="polite">
        <button type="button" className="btn" disabled={busy || blocking.length > 0} onClick={() => void merge()}
          aria-label={`Merge ${victim.candidate_code} into ${survivor.candidate_code}`}>{busy ? "Merging…" : "Merge"}</button>
        <Link className="btn secondary" href={`${CANDIDATES_PATH}/duplicates`}>Cancel</Link>
      </div>
    </section>
  );
}
