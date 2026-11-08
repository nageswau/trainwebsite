"use client";

import { useEffect, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import type { CardTag } from "@/lib/recruiterCandidateSearch";
import { candidateUrl } from "@/lib/recruiterCandidates";

type Tags = { items: CardTag[]; can_edit: boolean };
const MAX = 20;
const tagLabel = (t: CardTag) => (t.active ? t.name : `${t.name} (inactive)`);

/** pob-019 (DEC-SCOPE-437 T2): the candidate's free tags. Every reader sees them; a writer edits the whole set from the active "Candidate
 *  tags" list (a deactivated tag already on the candidate can stay). The API decides every rule. */
export default function RecruiterCandidateTags({ candidateId }: { candidateId: string }) {
  const id = useId();
  const [data, setData] = useState<Tags | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [options, setOptions] = useState<CatalogueValue[] | null>(null);
  const [chosen, setChosen] = useState<string[] | null>(null); // the draft while editing
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed?: boolean } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(candidateUrl(candidateId, "/tags"), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: Tags) => setData({ items: Array.isArray(body?.items) ? body.items : [], can_edit: !!body?.can_edit }))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  useEffect(() => {
    if (chosen === null || options !== null) return;
    const controller = new AbortController();
    activeValues("candidate-tags", controller.signal).then(setOptions).catch(() => controller.signal.aborted || setOptions([]));
    return () => controller.abort();
  }, [chosen, options]);

  async function save() {
    if (chosen === null || saving) return;
    setSaving(true);
    setNotice(null);
    const outcome = await sendJson(candidateUrl(candidateId, "/tags"), "PUT", { tag_ids: chosen });
    setSaving(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    setData(outcome.data as unknown as Tags);
    setChosen(null);
    setNotice({ text: "Tags saved." });
  }

  const current = data?.items ?? [];
  // the choices: every active tag, plus the inactive ones already on the candidate (they may stay)
  const choices: CardTag[] = [...current.filter((t) => !t.active), ...(options ?? []).map((o) => ({ id: o.id, name: o.name, active: true }))];
  const toggle = (tagId: string, on: boolean) => setChosen((c) => (on ? [...(c ?? []), tagId] : (c ?? []).filter((x) => x !== tagId)));

  return (
    <section className="action-card wide" aria-labelledby={`${id}-heading`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`${id}-heading`} style={{ margin: 0 }}>Tags</h3>
        {data?.can_edit && chosen === null && (
          <button type="button" className="btn secondary small" onClick={() => { setChosen(current.map((t) => t.id)); setNotice(null); }}>Edit tags</button>
        )}
      </div>
      <div role="status" aria-live="polite">{notice && !notice.failed && <p className="form-message" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}</div>
      {notice?.failed && <p className="form-error" role="alert" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the tags.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" style={{ fontSize: 13 }}>Loading tags…</p>
      ) : chosen !== null ? (
        <fieldset style={{ border: 0, padding: 0, margin: "8px 0 0" }} disabled={saving}>
          <legend className="visually-hidden">Choose the candidate&apos;s tags</legend>
          {options === null ? <p className="muted" style={{ fontSize: 13 }}>Loading the tag list…</p> : choices.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No candidate tags yet. A manager adds them under Catalogue → Candidate tags.</p>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px" }}>
              {choices.map((t) => (
                <label key={t.id} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" checked={chosen.includes(t.id)} disabled={!chosen.includes(t.id) && chosen.length >= MAX}
                    onChange={(e) => toggle(t.id, e.target.checked)} /> {tagLabel(t)}
                </label>
              ))}
            </div>
          )}
          {chosen.length >= MAX && <p className="muted" style={{ fontSize: 13 }}>A candidate can have up to {MAX} tags.</p>}
          <div className="actions" style={{ gap: 8, marginTop: 8 }}>
            <button type="button" className="btn small" onClick={save}>{saving ? "Saving…" : "Save tags"}</button>
            <button type="button" className="btn secondary small" onClick={() => setChosen(null)}>Cancel</button>
          </div>
        </fieldset>
      ) : current.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>No tags yet.</p>
      ) : (
        <ul aria-label="Candidate tags" style={{ listStyle: "none", padding: 0, margin: "8px 0 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
          {current.map((t) => <li key={t.id} className="badge">{tagLabel(t)}</li>)}
        </ul>
      )}
    </section>
  );
}
