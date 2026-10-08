"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import CreateJumpLink from "@/components/CreateJumpLink";
import RecruiterSkillCategories from "@/components/RecruiterSkillCategories";
import RecruiterSkillCategoryFields from "@/components/RecruiterSkillCategoryFields";
import RecruiterSkillDetail from "@/components/RecruiterSkillDetail";
import { sendJson, type Page } from "@/lib/apiErrors";
import { allCategories, categoryLabel, SKILLS_PAGE_SIZE, SKILLS_URL, skillsQuery, type Skill, type SkillCategory } from "@/lib/recruiterSkills";
import { formText, pageOffset, statusLabel } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "skill-create-feedback";

// rec-006 (DEC-SCOPE-118): the Skills Master. Recruiters (canEdit=false) read and search it; placement managers and super_admin also
// manage categories, create skills and open a skill to edit it. The search, category filter and page live in the URL (?q=&category=
// &offset=), so refresh keeps the place and Back returns to the previous view. The API decides who may write.
export default function RecruiterSkillsPanel({ canEdit }: { canEdit: boolean }) {
  const [data, setData] = useState<Page<Skill> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [categories, setCategories] = useState<SkillCategory[]>([]);
  const [categoryVersion, setCategoryVersion] = useState(0);
  const [selected, setSelected] = useState<Skill | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [formKey, setFormKey] = useState(0);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const offset = pageOffset(params.get("offset") ?? undefined);

  function go(next: { q: string; category: string; offset: number }) {
    const query = new URLSearchParams();
    if (next.q) query.set("q", next.q);
    if (next.category) query.set("category", next.category);
    if (next.offset > 0) query.set("offset", String(next.offset));
    router.push(query.size ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    getPage<Skill>(`${SKILLS_URL}?${skillsQuery({ q, category, offset }, SKILLS_PAGE_SIZE)}`, controller.signal)
      .then(setData)
      .catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [q, category, offset, version]);

  useEffect(() => {
    const controller = new AbortController();
    allCategories(controller.signal).then(setCategories).catch(() => controller.signal.aborted || setCategories([]));
    return () => controller.abort();
  }, [categoryVersion]);

  const reload = () => setVersion((v) => v + 1);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    const body = { name, category_id: formText(form, "category_id"), tag_category_ids: form.getAll("tag_category_ids").map(String) };
    setBusy(true);
    const outcome = await sendJson(SKILLS_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${name}.`, tone: "success" });
      setFormKey((k) => k + 1);
      reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    go({ q: formText(form, "q"), category: formText(form, "category"), offset: 0 });
  }

  function open(skill: Skill) {
    setSelected(skill);
  }

  function close() {
    const id = selected?.id;
    setSelected(null);
    if (id) focus(`skill-manage-${id}`);
  }

  const filtered = Boolean(q || category);
  return (
    <>
      {canEdit && <RecruiterSkillCategories categories={categories} onChanged={() => { setCategoryVersion((v) => v + 1); reload(); }} />}
      {canEdit && (
        <form key={formKey} className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
          <h3>Create skill</h3>
          <div className="field"><label htmlFor="skill-new-name">Skill name (required)</label><input id="skill-new-name" name="name" required maxLength={80} disabled={busy} /></div>
          <RecruiterSkillCategoryFields idPrefix="skill-new" categories={categories} disabled={busy} />
          <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create skill"}</button>
          <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
            {feedback?.text}
          </div>
        </form>
      )}
      {selected && (
        <RecruiterSkillDetail
          skill={selected}
          categories={categories}
          onChanged={(updated) => { if (updated) setSelected(updated); reload(); }}
          onClose={close}
        />
      )}
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Skills</h3>
        {canEdit && <CreateJumpLink targetId="skill-new-name" label="Create skill" />}
        <form key={`${q}|${category}|${categories.length}`} onSubmit={search} role="search" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
          <div className="field" style={{ flex: "1 1 200px", marginBottom: 0 }}>
            <label htmlFor="skill-q">Search skills or aliases</label>
            <input id="skill-q" name="q" type="search" defaultValue={q} maxLength={200} />
          </div>
          <div className="field" style={{ flex: "1 1 180px", marginBottom: 0 }}>
            <label htmlFor="skill-filter">Category</label>
            <select id="skill-filter" name="category" defaultValue={category}>
              <option value="">All categories</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}{c.active ? "" : " (inactive)"}</option>)}
            </select>
          </div>
          <button className="btn secondary small">Search</button>
          {filtered && <button type="button" className="btn secondary small" onClick={() => go({ q: "", category: "", offset: 0 })}>Clear</button>}
        </form>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load skills.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading skills…</p>
        ) : data.items.length === 0 ? (
          <p className="empty" role="status">{filtered ? "No skills match your search." : offset > 0 ? "This page is past the end of the list." : "No skills yet."}</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Skills" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Skill</th><th scope="col">Category</th><th scope="col">Aliases</th><th scope="col">Related</th><th scope="col">Status</th>
                    {canEdit && <th scope="col"><span className="visually-hidden">Actions</span></th>}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr key={s.id}>
                      <td data-label="Skill">{s.name}</td>
                      <td data-label="Category">{categoryLabel(s)}</td>
                      <td data-label="Aliases">{s.aliases.map((a) => a.alias).join(", ") || "—"}</td>
                      <td data-label="Related">{s.related.map((r) => r.name).join(", ") || "—"}</td>
                      <td data-label="Status"><span className="badge">{statusLabel(s.active)}</span></td>
                      {canEdit && (
                        <td data-label="Actions">
                          <button id={`skill-manage-${s.id}`} type="button" className="btn secondary small" aria-label={`Manage ${s.name}`} onClick={() => open(s)}>Manage</button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > SKILLS_PAGE_SIZE && (
              <nav aria-label="Skill pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go({ q, category, offset: Math.max(0, offset - SKILLS_PAGE_SIZE) })}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ q, category, offset: offset + SKILLS_PAGE_SIZE })}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
