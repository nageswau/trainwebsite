"use client";
import { useEffect, useId, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { LEVELS, type SkillLevel } from "@/lib/recruiterCandidateSkills";
import { experienceLabel } from "@/lib/recruiterCandidates";
import {
  type ApplyResult, applyBody, applyUrl, type CurrentProfile, type Extraction, extractUrl, FIELD_LABEL, hasChoice, initialSelection, PROFILE_KEYS,
  type ProfileKey, savedMessage, type Selection,
} from "@/lib/recruiterResumeExtract";

type Props = { candidateId: string; version: number; current: CurrentProfile; onApplied: (message: string) => void; onClose: () => void };

const shown = (key: ProfileKey, value: string | number | null) => (value === null || value === "" ? "—" : key === "experience_months" ? experienceLabel(value as number) : String(value));

/** rec-012 (spec §5): "Review extracted details" for one resume version. Extract runs on open (and on Retry); nothing reaches the profile
 *  until Save selected (AC2). Skills already on the profile are shown but cannot be ticked; a profile field is ticked by default only
 *  when the candidate has no value. A refusal keeps the ticks and shows the server's sentence. */
export default function RecruiterResumeExtraction({ candidateId, version, current, onApplied, onClose }: Props) {
  const [data, setData] = useState<Extraction | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const id = useId();

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setLoadError(null);
    void sendRequest(extractUrl(candidateId, version), { method: "POST", signal: controller.signal }).then((outcome) => {
      if (controller.signal.aborted) return;
      if (!outcome.ok) return setLoadError(outcome.message);
      const extraction = outcome.data as unknown as Extraction;
      setData(extraction);
      setSelection(initialSelection(extraction, current));
    });
    return () => controller.abort();
    // `current` seeds the default ticks once per extraction; a later profile reload must not reset what the recruiter ticked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId, version, attempt]);

  async function save() {
    if (!data || !selection || sending.current) return;
    sending.current = true;
    setBusy(true);
    setSaveError(null);
    const outcome = await sendJson(applyUrl(candidateId, version), "POST", applyBody(data, selection));
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setSaveError(outcome.message);
    onApplied(savedMessage(outcome.data as unknown as ApplyResult));
  }

  const heading = <h4 id={`${id}-heading`} style={{ margin: 0 }}>Review extracted details — version {version}</h4>;
  if (loadError) {
    return (
      <section aria-labelledby={`${id}-heading`} className="action-card" style={{ display: "grid", gap: 8 }}>
        {heading}
        <p className="form-error" role="alert" style={{ margin: 0 }}>{loadError}</p>
        <div className="actions">
          <button type="button" className="btn secondary small" onClick={() => setAttempt((n) => n + 1)}>Retry</button>
          <button type="button" className="btn secondary small" onClick={onClose}>Close</button>
        </div>
      </section>
    );
  }
  if (!data || !selection) {
    return (
      <section aria-labelledby={`${id}-heading`} aria-busy="true" className="action-card" style={{ display: "grid", gap: 8 }}>
        {heading}
        <p className="muted" role="status" style={{ margin: 0 }}>Reading the resume…</p>
      </section>
    );
  }
  if (data.no_text) {
    return (
      <section aria-labelledby={`${id}-heading`} className="action-card" style={{ display: "grid", gap: 8 }}>
        {heading}
        <p role="status" style={{ margin: 0 }}>No text found in this resume — it may be a scanned image. Add the details by hand.</p>
        <div className="actions"><button type="button" className="btn secondary small" onClick={onClose}>Close</button></div>
      </section>
    );
  }

  const body = applyBody(data, selection);
  const suggested = PROFILE_KEYS.filter((k) => data[k] !== null);
  const extras: [string, string[]][] = [["Job titles", data.job_titles], ["Certifications", data.certifications], ["Industry", data.industries]];
  const setSkill = (skillId: string, ticked: boolean) => setSelection({ ...selection, skills: { ...selection.skills, [skillId]: ticked } });
  const setLevel = (skillId: string, level: SkillLevel) => setSelection({ ...selection, levels: { ...selection.levels, [skillId]: level } });
  const setField = (key: ProfileKey, ticked: boolean) => setSelection({ ...selection, fields: { ...selection.fields, [key]: ticked } });

  return (
    <section aria-labelledby={`${id}-heading`} className="action-card" style={{ display: "grid", gap: 12 }}>
      {heading}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Tick what is correct, then save. Nothing is added to the profile until you save.
        {data.truncated && " Only the first part of this long resume was read."}
      </p>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Skills found ({data.skills.length})</legend>
        {data.skills.length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>No skills from the Skills Master were found in this resume.</p>
        ) : data.skills.map((s) => {
          const name = s.skill.name;
          const box = `${id}-skill-${s.skill.id}`;
          return (
            <div key={s.skill.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
              <label htmlFor={box} style={{ display: "flex", gap: 8, alignItems: "baseline", flex: "1 1 14rem", minHeight: 24 }}>
                <input id={box} type="checkbox" checked={!s.on_profile && Boolean(selection.skills[s.skill.id])} disabled={s.on_profile || busy}
                  onChange={(event) => setSkill(s.skill.id, event.target.checked)} />
                <span>
                  {name} <span className="muted" style={{ fontSize: 12 }}>{s.category.name}</span>
                  {s.matched.toLowerCase() !== name.toLowerCase() && <span className="muted" style={{ fontSize: 12, display: "block" }}>found as “{s.matched}”</span>}
                </span>
              </label>
              {s.on_profile ? <span className="badge">Already on profile</span> : (
                <select aria-label={`Level for ${name}`} value={selection.levels[s.skill.id]} disabled={busy || !selection.skills[s.skill.id]}
                  onChange={(event) => setLevel(s.skill.id, event.target.value as SkillLevel)}>
                  {LEVELS.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              )}
            </div>
          );
        })}
      </fieldset>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Profile details</legend>
        {suggested.length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>No qualification, experience or location was found.</p>
        ) : suggested.map((key) => (
          <label key={key} htmlFor={`${id}-${key}`} style={{ display: "flex", gap: 8, alignItems: "baseline", minHeight: 24 }}>
            <input id={`${id}-${key}`} type="checkbox" checked={selection.fields[key]} disabled={busy} onChange={(event) => setField(key, event.target.checked)} />
            <span>
              {FIELD_LABEL[key]}: {shown(key, data[key])}{" "}
              <span className="muted" style={{ fontSize: 12 }}>(current: {shown(key, current[key])})</span>
            </span>
          </label>
        ))}
      </fieldset>
      {extras.some(([, values]) => values.length > 0) && (
        <div>
          <p style={{ fontWeight: 600, margin: "0 0 4px" }}>Also in the resume <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>(kept with the resume, not added to the profile)</span></p>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "8px 16px", margin: 0 }}>
            {extras.filter(([, values]) => values.length > 0).map(([term, values]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0 }}>
                  <ul style={{ margin: 0, paddingLeft: 18, overflowWrap: "anywhere" }}>{values.map((v) => <li key={v}>{v}</li>)}</ul>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {saveError && <p className="form-error" role="alert" style={{ margin: 0 }}>{saveError}</p>}
      <div className="actions">
        <button type="button" className="btn small" onClick={() => void save()} disabled={busy || !hasChoice(body)}>{busy ? "Saving…" : "Save selected"}</button>
        <button type="button" className="btn secondary small" onClick={onClose} disabled={busy}>Discard</button>
      </div>
    </section>
  );
}
