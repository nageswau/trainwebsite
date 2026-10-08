"use client";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { SKILL_CATEGORIES_URL, type SkillCategory } from "@/lib/recruiterSkills";
import { formText, statusLabel } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "skill-cat-feedback";

// rec-006 (S2-§2 "admin should be able to add/edit"): the manager's category list -- add, rename inline (Esc cancels), deactivate and
// reactivate. Categories are never deleted; a deactivated one stays on the skills that use it.
export default function RecruiterSkillCategories({ categories, onChanged }: { categories: SkillCategory[]; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const inFlight = useRef(false); // `busy` disables the buttons only after a re-render; a double click must not write twice
  const focus = useFocusAfterRender();

  async function write(url: string, method: "POST" | "PATCH", body: Record<string, unknown>, success: string) {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(url, method, body);
    inFlight.current = false;
    setBusy(false);
    setFeedback(outcome.ok ? { text: success, tone: "success" } : { text: outcome.message, tone: "error" });
    focus(FEEDBACK_ID);
    if (outcome.ok) onChanged();
    return outcome.ok;
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const name = formText(new FormData(formEl), "name");
    if (await write(SKILL_CATEGORIES_URL, "POST", { name }, `Added category ${name}.`)) formEl.reset();
  }

  async function rename(event: React.FormEvent<HTMLFormElement>, category: SkillCategory) {
    event.preventDefault();
    const name = formText(new FormData(event.currentTarget), "name");
    if (await write(`${SKILL_CATEGORIES_URL}/${category.id}`, "PATCH", { name }, `Renamed to ${name}.`)) setEditing(null);
  }

  return (
    <section className="action-card wide telecaller-list" aria-labelledby="skill-cat-title">
      <h3 id="skill-cat-title">Categories</h3>
      <form className="form" onSubmit={create} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 220px", marginBottom: 0 }}>
          <label htmlFor="skill-cat-name">Category name (required)</label>
          <input id="skill-cat-name" name="name" required maxLength={80} disabled={busy} />
        </div>
        <button className="btn" disabled={busy}>Add category</button>
      </form>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ margin: "8px 0", overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
      <div className="table-wrap" role="region" aria-label="Category list" tabIndex={0}>
        <table>
          <thead><tr><th scope="col">Name</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id}>
                {editing === c.id ? (
                  <td colSpan={3}>
                    <form className="form" onSubmit={(e) => rename(e, c)} onKeyDown={(e) => { if (e.key === "Escape") { setEditing(null); focus(`skill-cat-edit-${c.id}`); } }}
                      style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                      <div className="field" style={{ flex: "1 1 200px", marginBottom: 0 }}>
                        <label htmlFor={`skill-cat-rename-${c.id}`}>New name for {c.name}</label>
                        <input id={`skill-cat-rename-${c.id}`} name="name" defaultValue={c.name} required maxLength={80} autoFocus disabled={busy} />
                      </div>
                      <button className="btn small" disabled={busy}>Save</button>
                      <button type="button" className="btn secondary small" onClick={() => { setEditing(null); focus(`skill-cat-edit-${c.id}`); }} disabled={busy}>Cancel</button>
                    </form>
                  </td>
                ) : (
                  <>
                    <td data-label="Name">{c.name}</td>
                    <td data-label="Status"><span className="badge">{statusLabel(c.active)}</span></td>
                    <td data-label="Actions">
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button id={`skill-cat-edit-${c.id}`} type="button" className="btn secondary small" aria-label={`Rename ${c.name}`} onClick={() => setEditing(c.id)} disabled={busy}>Rename</button>
                        <button type="button" className="btn secondary small" aria-label={`${c.active ? "Deactivate" : "Reactivate"} ${c.name}`} disabled={busy}
                          onClick={() => write(`${SKILL_CATEGORIES_URL}/${c.id}`, "PATCH", { active: !c.active }, `${c.active ? "Deactivated" : "Reactivated"} ${c.name}.`)}>
                          {c.active ? "Deactivate" : "Reactivate"}
                        </button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
