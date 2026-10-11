"use client";
import { useEffect, useId, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { isProgramSkills, type ProgramSkill, type ProgramSkillsSaved, programSkillOptions, programSkillsUrl } from "@/lib/programSkills";

type Notice = { text: string; failed: boolean } | null;

/** rec-036 (CI1): the skills a program teaches. The IT admin picks Skills Master skills, removes chips, and saves the whole set; a new
 *  skill reaches the program's opted-in certificate holders as "Course completed" (CI3). Nothing is sent until Save. */
export default function ProgramSkillsEditor({ programId, programTitle, onClose }: { programId: string; programTitle: string; onClose: () => void }) {
  const [skills, setSkills] = useState<ProgramSkill[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [pickerKey, setPickerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const sending = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const id = useId();

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(programSkillsUrl(programId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isProgramSkills(body) ? setSkills(body.items) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [programId, version]);

  useEffect(() => headingRef.current?.focus(), [programId]);

  function add(option: PickOption | null) {
    if (!option || !skills) return;
    if (!skills.some((s) => s.id === option.id)) setSkills([...skills, { id: option.id, name: option.label, active: true, category: option.detail ?? "" }]);
    setNotice(null);
    setPickerKey((n) => n + 1); // a fresh, empty picker for the next skill
  }

  async function save() {
    if (!skills || sending.current) return;
    sending.current = true;
    setBusy(true);
    setNotice(null);
    const outcome = await sendJson(programSkillsUrl(programId), "PUT", { skill_ids: skills.map((s) => s.id) });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    const saved = outcome.data as unknown as ProgramSkillsSaved;
    setSkills(saved.items);
    const n = saved.candidates_updated;
    setNotice({ text: `Skills saved.${n ? ` ${n} candidate${n === 1 ? " was" : "s were"} updated.` : ""}`, failed: false });
  }

  return (
    <section className="action-card" aria-labelledby={`${id}-heading`} style={{ marginTop: 12, display: "grid", gap: 8 }}>
      <h4 id={`${id}-heading`} ref={headingRef} tabIndex={-1} style={{ margin: 0, overflowWrap: "anywhere" }}>Skills taught in {programTitle}</h4>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Students who hold this program&apos;s certificate and have joined the placement pool get these skills as &ldquo;Course completed&rdquo;.
        Removing a skill here does not remove it from candidates.
      </p>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the program&apos;s skills.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : skills === null ? (
        <p className="muted" role="status" style={{ fontSize: 13, margin: 0 }}>Loading skills…</p>
      ) : (
        <>
          {skills.length === 0 ? (
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>No skills yet. Add the skills this program teaches.</p>
          ) : (
            <ul aria-label="Skills taught" style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: 0, margin: 0 }}>
              {skills.map((s) => (
                <li key={s.id} className="badge" style={{ listStyle: "none", display: "inline-flex", alignItems: "center", gap: 6, maxWidth: "100%" }}>
                  <span style={{ overflowWrap: "anywhere" }}>{s.name}{s.active ? "" : " (inactive)"}</span>
                  <button type="button" className="btn secondary small" aria-label={`Remove ${s.name}`} disabled={busy}
                    onClick={() => { setSkills(skills.filter((x) => x.id !== s.id)); setNotice(null); }} style={{ padding: "0 6px", minHeight: 24 }}>×</button>
                </li>
              ))}
            </ul>
          )}
          <SearchableSelect key={pickerKey} id={`${id}-pick`} label="Add a skill" noun="skill" search={programSkillOptions} onChange={add} disabled={busy} />
          {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
        </>
      )}
      <div className="actions">
        {skills !== null && !failed && <button type="button" className="btn small" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save skills"}</button>}
        <button type="button" className="btn secondary small" onClick={onClose} disabled={busy}>Close</button>
      </div>
    </section>
  );
}
