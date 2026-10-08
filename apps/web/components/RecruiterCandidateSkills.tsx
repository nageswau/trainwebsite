"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import {
  type CandidateSkill, type CandidateSkillList, candidateSkillsUrl, EMPTY_SKILL_FORM, formOf, LEVEL_LABEL, LEVELS, SOURCE_LABEL, SOURCES,
  type SkillForm, statusActions, STATUS_LABEL, toBody,
} from "@/lib/recruiterCandidateSkills";
import { experienceLabel } from "@/lib/recruiterCandidates";
import { skillSearch } from "@/lib/recruiterSkills";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Notice = { text: string; failed: boolean } | null;

/** Add (with the Skills Master picker) or edit one skill. The entry is kept on a refusal; the server's sentence is shown as is. */
function SkillFormCard({ candidateId, editing, onCancel, onSaved }: {
  candidateId: string; editing: CandidateSkill | null; onCancel: () => void; onSaved: (text: string) => void;
}) {
  const [form, setForm] = useState<SkillForm>(editing ? formOf(editing) : EMPTY_SKILL_FORM);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const id = useId();
  const title = editing ? `Edit ${editing.skill.name}` : "Add skill";
  const set = (key: keyof SkillForm) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: event.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!editing && !picked) return setError("Choose a skill from the list.");
    if (!form.level) return setError("Choose a level.");
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    const name = editing ? editing.skill.name : picked!.label;
    const outcome = editing
      ? await sendJson(candidateSkillsUrl(candidateId, editing.id), "PATCH", toBody(form, false))
      : await sendJson(candidateSkillsUrl(candidateId), "POST", toBody({ ...form, skill: name }, true));
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    onSaved(editing ? `Saved ${name}.` : `Added ${name}.`);
  }

  return (
    <form aria-label={title} onSubmit={submit} className="form" style={{ display: "grid", gap: 8, marginTop: 8 }}>
      {editing ? <strong>{title}</strong> : (
        <SearchableSelect id={`${id}-skill`} label="Skill (required)" noun="skill" search={skillSearch("")} onChange={setPicked} disabled={busy} />
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <div className="field" style={{ flex: "1 1 10rem", marginBottom: 0 }}>
          <label htmlFor={`${id}-level`}>Level (required)</label>
          <select id={`${id}-level`} value={form.level} onChange={set("level")} disabled={busy}>
            <option value="">Choose…</option>
            {LEVELS.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
          </select>
        </div>
        <div className="field" style={{ flex: "1 1 10rem", marginBottom: 0 }}>
          <label htmlFor={`${id}-exp`}>Experience (months)</label>
          <input id={`${id}-exp`} type="number" inputMode="numeric" min={0} max={600} value={form.experience_months} onChange={set("experience_months")} disabled={busy} />
        </div>
        <div className="field" style={{ flex: "1 1 10rem", marginBottom: 0 }}>
          <label htmlFor={`${id}-year`}>Last used (year)</label>
          <input id={`${id}-year`} type="number" inputMode="numeric" min={1950} max={new Date().getFullYear()} value={form.last_used_year} onChange={set("last_used_year")} disabled={busy} />
        </div>
        <div className="field" style={{ flex: "1 1 12rem", marginBottom: 0 }}>
          <label htmlFor={`${id}-source`}>Source</label>
          <select id={`${id}-source`} value={form.source} onChange={set("source")} disabled={busy}>
            {SOURCES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="actions">
        <button className="btn small" disabled={busy}>{busy ? "Saving…" : editing ? "Save" : "Add"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

/** rec-011 (spec §6): the candidate's Skills card -- one row per skill (AC1), Add from the Skills Master (SK5), Edit, the status moves
 *  that record who and when (AC3), and Remove with a confirm. `can_edit` (from the API: a writer on an active candidate) decides the
 *  controls, so hr_team and an archived candidate read only. */
export default function RecruiterCandidateSkills({ candidateId }: { candidateId: string }) {
  const [data, setData] = useState<CandidateSkillList | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const focus = useFocusAfterRender();
  const id = useId();
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(candidateSkillsUrl(candidateId), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then(setData)
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  function done(text: string, failedWrite = false) {
    setNotice({ text, failed: failedWrite });
    focus(`${id}-feedback`);
    if (!failedWrite) {
      setAdding(false);
      setEditingId(null);
      setRemovingId(null);
    }
    reload();
  }

  async function run(request: () => Promise<SendOutcome>, success: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    const outcome = await request();
    sending.current = false;
    setBusy(false);
    done(outcome.ok ? success : outcome.message, !outcome.ok);
  }

  const canEdit = data?.can_edit ?? false;
  const columns = canEdit ? 7 : 6;
  return (
    <section className="action-card wide telecaller-list" aria-labelledby={`${id}-heading`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`${id}-heading`} style={{ margin: 0 }}>Skills</h3>
        {canEdit && !adding && (
          <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setEditingId(null); setNotice(null); }}>Add skill</button>
        )}
      </div>
      <div id={`${id}-feedback`} tabIndex={-1} role="status" aria-live="polite">
        {notice && !notice.failed && <p className="form-message" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      </div>
      {notice?.failed && <p className="form-error" role="alert" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice.text}</p>}
      {adding && canEdit && <SkillFormCard candidateId={candidateId} editing={null} onCancel={() => setAdding(false)} onSaved={(text) => done(text)} />}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the skills.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" style={{ fontSize: 13 }}>Loading skills…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: "8px 0 0" }}>No skills added yet.</p>
      ) : (
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table aria-label="Skills">
            <thead>
              <tr><th>Skill</th><th>Level</th><th>Experience</th><th>Last used</th><th>Source</th><th>Status</th>{canEdit && <th>Actions</th>}</tr>
            </thead>
            <tbody>
              {data.items.flatMap((s) => {
                const name = s.skill.name;
                const row = (
                  <tr key={s.id}>
                    <td data-label="Name">
                      {name}{s.skill.active ? "" : " (inactive)"}
                      <div className="muted" style={{ fontSize: 12, fontWeight: 400 }}>{s.category.name}</div>
                    </td>
                    <td data-label="Level">{LEVEL_LABEL[s.level] ?? s.level}</td>
                    <td data-label="Experience">{s.experience_months === null ? "—" : experienceLabel(s.experience_months)}</td>
                    <td data-label="Last used">{s.last_used_year ?? "—"}</td>
                    <td data-label="Source">{SOURCE_LABEL[s.source] ?? s.source}</td>
                    <td data-label="Status">
                      <span>
                        <span className="badge">{STATUS_LABEL[s.status]}</span>
                        {s.verified_by && <span className="muted" style={{ fontSize: 12 }}> by {s.verified_by.full_name} · <LocalTime value={s.verified_at} /></span>}
                      </span>
                    </td>
                    {canEdit && (
                      <td data-label="Actions">
                        {removingId === s.id ? (
                          <div role="group" aria-label={`Confirm removing ${name}`} className="actions">
                            <span>Remove {name} from this candidate?</span>
                            <button type="button" className="btn small" disabled={busy}
                              onClick={() => void run(() => sendRequest(candidateSkillsUrl(candidateId, s.id), { method: "DELETE" }), `Removed ${name}.`)}>Yes, remove</button>
                            <button type="button" className="btn secondary small" disabled={busy} onClick={() => setRemovingId(null)}>Keep it</button>
                          </div>
                        ) : (
                          <div className="actions">
                            <button type="button" className="btn secondary small" aria-label={`Edit ${name}`} disabled={busy}
                              onClick={() => { setEditingId(s.id); setAdding(false); setNotice(null); }}>Edit</button>
                            {statusActions(s.status).map((a) => (
                              <button key={a.status} type="button" className="btn secondary small" aria-label={`${a.label}: ${name}`} disabled={busy}
                                onClick={() => void run(() => sendJson(candidateSkillsUrl(candidateId, s.id, "/status"), "POST", { status: a.status }), `${name} marked ${a.status}.`)}>
                                {a.label}
                              </button>
                            ))}
                            <button type="button" className="btn secondary small" aria-label={`Remove ${name}`} disabled={busy}
                              onClick={() => { setRemovingId(s.id); setNotice(null); }}>Remove</button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                );
                return editingId === s.id ? [row, (
                  <tr key={`${s.id}-edit`}>
                    <td colSpan={columns}>
                      <SkillFormCard candidateId={candidateId} editing={s} onCancel={() => setEditingId(null)} onSaved={(text) => done(text)} />
                    </td>
                  </tr>
                )] : [row];
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
