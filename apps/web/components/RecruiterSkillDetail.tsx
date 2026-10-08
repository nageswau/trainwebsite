"use client";
import { useEffect, useRef, useState } from "react";

import RecruiterSkillCategoryFields from "@/components/RecruiterSkillCategoryFields";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { SKILLS_URL, skillSearch, type Skill, type SkillCategory } from "@/lib/recruiterSkills";
import { formText } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

// rec-006: one skill, opened from the list by a manager -- rename / category / other categories, aliases (S2-§16), related skills
// (S4) and deactivate/reactivate. Every write's answer is the updated skill (or, for a removal, the list reloads it); the server decides
// conflicts and its sentence is shown as is.
export default function RecruiterSkillDetail({ skill, categories, onChanged, onClose }: {
  skill: Skill;
  categories: SkillCategory[];
  onChanged: (updated: Skill | null) => void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [related, setRelated] = useState<PickOption | null>(null);
  const [pickerKey, setPickerKey] = useState(0);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();
  const id = (name: string) => `skill-${name}-${skill.id}`;
  const url = `${SKILLS_URL}/${skill.id}`;

  useEffect(() => {
    document.getElementById(id("title"))?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- focus the heading once, when this skill opens
  }, [skill.id]);

  async function run(request: () => Promise<SendOutcome>, success: string, removal = false) {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    const outcome = await request();
    inFlight.current = false;
    setBusy(false);
    setConfirming(false);
    setFeedback(outcome.ok ? { text: success, tone: "success" } : { text: outcome.message, tone: "error" });
    focus(id("feedback"));
    if (outcome.ok) onChanged(removal ? null : (outcome.data as Skill));
    return outcome.ok;
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    const body = { name, category_id: formText(form, "category_id"), tag_category_ids: form.getAll("tag_category_ids").map(String) };
    await run(() => sendJson(url, "PATCH", body), `Saved ${name}.`);
  }

  async function addAlias(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const alias = formText(new FormData(formEl), "alias");
    if (await run(() => sendJson(`${url}/aliases`, "POST", { alias }), `Added alias ${alias}.`)) formEl.reset();
  }

  async function addRelated(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!related) {
      setFeedback({ text: "Choose a skill from the list.", tone: "error" });
      focus(id("feedback"));
      return;
    }
    if (await run(() => sendJson(`${url}/related`, "POST", { skill_id: related.id }), `Related ${skill.name} to ${related.label}.`)) {
      setRelated(null);
      setPickerKey((k) => k + 1);
    }
  }

  const remove = (path: string, success: string) => run(() => sendRequest(`${url}/${path}`, { method: "DELETE" }), success, true);
  const chip = { display: "inline-flex", alignItems: "center", gap: 4 } as const;

  return (
    <section className="action-card wide form" aria-labelledby={id("title")}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <h3 id={id("title")} tabIndex={-1}>{skill.name}</h3>
        <button type="button" className="btn secondary small" aria-label={`Close ${skill.name}`} onClick={onClose}>Close</button>
      </div>
      <div id={id("feedback")} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>

      <form key={`${skill.id}-${skill.name}-${skill.category.id}-${skill.tags.map((t) => t.id).join()}`} onSubmit={save}>
        <div className="field"><label htmlFor={id("name")}>Skill name (required)</label><input id={id("name")} name="name" defaultValue={skill.name} required maxLength={80} disabled={busy} /></div>
        <RecruiterSkillCategoryFields idPrefix={id("edit")} categories={categories} current={skill} disabled={busy} />
        <button className="btn small" disabled={busy}>Save skill</button>
      </form>

      <h4 style={{ marginTop: 16 }}>Aliases</h4>
      <p className="muted" style={{ fontSize: 13 }}>Other spellings that find this skill (for example J2EE for Java).</p>
      {skill.aliases.length === 0 ? <p className="muted">No aliases yet.</p> : (
        <ul aria-label={`Aliases of ${skill.name}`} style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", padding: 0 }}>
          {skill.aliases.map((a) => (
            <li key={a.id} className="badge" style={chip}>
              {a.alias}
              <button type="button" className="btn secondary small" aria-label={`Remove alias ${a.alias}`} disabled={busy} onClick={() => remove(`aliases/${a.id}`, `Removed alias ${a.alias}.`)}>×</button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={addAlias} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 200px", marginBottom: 0 }}><label htmlFor={id("alias")}>New alias</label><input id={id("alias")} name="alias" required maxLength={80} disabled={busy} /></div>
        <button className="btn small" disabled={busy}>Add alias</button>
      </form>

      <h4 style={{ marginTop: 16 }}>Related skills</h4>
      <p className="muted" style={{ fontSize: 13 }}>Skills a search can widen to (for example Core Java for Java). Related works both ways.</p>
      {skill.related.length === 0 ? <p className="muted">No related skills yet.</p> : (
        <ul aria-label={`Skills related to ${skill.name}`} style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", padding: 0 }}>
          {skill.related.map((r) => (
            <li key={r.id} className="badge" style={chip}>
              {r.name}{r.active ? "" : " (inactive)"}
              <button type="button" className="btn secondary small" aria-label={`Remove related skill ${r.name}`} disabled={busy} onClick={() => remove(`related/${r.id}`, `Removed ${r.name}.`)}>×</button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={addRelated} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 240px" }}>
          <SearchableSelect key={pickerKey} id={id("related")} label="Related skill" noun="skill" search={skillSearch(skill.id)} onChange={setRelated} disabled={busy} />
        </div>
        <button className="btn small" disabled={busy}>Add related skill</button>
      </form>

      <h4 style={{ marginTop: 16 }}>Status</h4>
      {skill.active ? (
        confirming ? (
          <div role="group" aria-label={`Confirm deactivating ${skill.name}`}>
            <p className="muted" style={{ fontSize: 13 }}>Recruiters stop seeing it and resume scans stop matching it. It is kept, with its aliases, and can be reactivated.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => run(() => sendJson(url, "PATCH", { active: false }), `Deactivated ${skill.name}.`)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => setConfirming(false)} disabled={busy}>Keep active</button>
          </div>
        ) : (
          <button type="button" className="btn secondary small" aria-label={`Deactivate ${skill.name}`} onClick={() => { setConfirming(true); focus(id("confirm")); }} disabled={busy}>Deactivate</button>
        )
      ) : (
        <button type="button" className="btn secondary small" aria-label={`Reactivate ${skill.name}`} onClick={() => run(() => sendJson(url, "PATCH", { active: true }), `Reactivated ${skill.name}.`)} disabled={busy}>Reactivate</button>
      )}
    </section>
  );
}
