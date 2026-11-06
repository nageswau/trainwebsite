"use client";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import RecruiterScreeningQuestions, { questionsProblem } from "@/components/RecruiterScreeningQuestions";
import { sendJson } from "@/lib/apiErrors";
import { type BankQuestion, blankDraft, type Catalogue, choiceList, draftBody, draftOf, LIMITS, questionBody, type QuestionDraft, QUESTIONS_URL, type Template, TEMPLATES_URL } from "@/lib/recruiterScreening";

type BankRead = Catalogue & { items: BankQuestion[]; total: number };
type TemplatesRead = Catalogue & { items: Template[] };
const PAGE = 50;
const field = { display: "grid", gap: 4 } as const;
const small = { margin: 0, fontSize: 13 } as const;

const fetchJson = async <T,>(url: string, signal?: AbortSignal): Promise<T> => {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
};

function QuestionEditor({ catalogue, question, onSaved, onCancel }: { catalogue: Catalogue; question?: BankQuestion; onSaved: () => void; onCancel: () => void }) {
  const [draft, setDraft] = useState(() => (question ? draftOf(question) : blankDraft()));
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const id = useId();
  const set = (patch: Partial<QuestionDraft>) => setDraft((d) => ({ ...d, ...patch }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    if (!draft.text.trim()) return setFailure("Write the question.");
    if (draft.format === "choice" && choiceList(draft.choices).length < 2) return setFailure("Give at least two choices.");
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const outcome = question ? await sendJson(`${QUESTIONS_URL}/${encodeURIComponent(question.id)}`, "PATCH", questionBody(draft)) : await sendJson(QUESTIONS_URL, "POST", questionBody(draft));
    sending.current = false;
    setBusy(false);
    if (outcome.ok) onSaved();
    else setFailure(outcome.message);
  }

  return (
    <form onSubmit={submit} aria-label={question ? "Edit a question" : "Add a question"} style={{ display: "grid", gap: 8 }}>
      <label htmlFor={`${id}-text`} style={field}>Question text<textarea id={`${id}-text`} rows={2} maxLength={LIMITS.text} value={draft.text} onChange={(e) => set({ text: e.target.value })} /></label>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <label htmlFor={`${id}-category`} style={field}>Category
          <select id={`${id}-category`} value={draft.category} onChange={(e) => set({ category: e.target.value })}>{catalogue.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        </label>
        <label htmlFor={`${id}-format`} style={field}>Answer format
          <select id={`${id}-format`} value={draft.format} onChange={(e) => set({ format: e.target.value })}>{catalogue.formats.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</select>
        </label>
      </div>
      {draft.format === "choice" && <label htmlFor={`${id}-choices`} style={field}>Choices (one per line)<textarea id={`${id}-choices`} rows={3} value={draft.choices} onChange={(e) => set({ choices: e.target.value })} /></label>}
      <label htmlFor={`${id}-criteria`} style={field}>What to look for<input id={`${id}-criteria`} maxLength={LIMITS.criteria} value={draft.evaluation_criteria} onChange={(e) => set({ evaluation_criteria: e.target.value })} /></label>
      <label htmlFor={`${id}-expected`} style={field}>Expected answer<input id={`${id}-expected`} maxLength={LIMITS.expected} value={draft.expected_answer} onChange={(e) => set({ expected_answer: e.target.value })} /></label>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save question"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function TemplateEditor({ catalogue, template, onSaved, onCancel }: { catalogue: Catalogue; template?: Template; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(template?.name ?? "");
  const [rows, setRows] = useState<QuestionDraft[]>(() => (template ? template.questions.map((q) => draftOf(q)) : [blankDraft()]));
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const problem = !name.trim() ? "Name the template." : questionsProblem(rows);
    if (problem) return setFailure(problem);
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const body = { name: name.trim(), questions: rows.map(draftBody) };
    const outcome = template ? await sendJson(`${TEMPLATES_URL}/${encodeURIComponent(template.id)}`, "PATCH", body) : await sendJson(TEMPLATES_URL, "POST", body);
    sending.current = false;
    setBusy(false);
    if (outcome.ok) onSaved();
    else setFailure(outcome.message);
  }

  return (
    <form onSubmit={submit} aria-label={template ? `Edit template ${template.name}` : "New template"} style={{ display: "grid", gap: 10 }}>
      <label htmlFor={`${id}-name`} style={field}>Template name<input id={`${id}-name`} maxLength={LIMITS.name} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <RecruiterScreeningQuestions rows={rows} catalogue={catalogue} onChange={setRows} />
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save template"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** pob-020 (DEC-SCOPE-414): the question bank and form templates. Editing here never changes a form that already copied a question. */
export default function RecruiterScreeningBank() {
  const [bank, setBank] = useState<BankRead | null>(null);
  const [templates, setTemplates] = useState<TemplatesRead | null>(null);
  const [failed, setFailed] = useState(false);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [archived, setArchived] = useState(false);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState<"question" | "template" | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // one question or template id at a time
  const [failure, setFailure] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const id = useId();
  const reload = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (query) params.set("q", query);
    if (category) params.set("category", category);
    if (archived) params.set("include_archived", "true");
    Promise.all([fetchJson<BankRead>(`${QUESTIONS_URL}?${params}`, controller.signal), fetchJson<TemplatesRead>(`${TEMPLATES_URL}?include_archived=${archived}`, controller.signal)])
      .then(([b, t]) => { setBank(b); setTemplates(t); setFailed(false); })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [query, category, archived, offset, reloads]);

  async function patch(url: string, body: unknown) {
    setFailure(null);
    const outcome = await sendJson(url, "PATCH", body);
    if (!outcome.ok) setFailure(outcome.message);
    reload();
  }

  if (failed) return <p className="form-error" role="alert">Unable to load the question bank.</p>;
  if (!bank || !templates) return <p className="muted" role="status">Loading question bank…</p>;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <section className="action-card wide" aria-labelledby={`${id}-bank`}>
        <h3 id={`${id}-bank`} style={{ margin: 0 }}>Question bank</h3>
        <form role="search" aria-label="Search the question bank" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }} onSubmit={(e) => { e.preventDefault(); setOffset(0); setQuery(search.trim()); }}>
          <label htmlFor={`${id}-q`} style={{ ...field, flex: "1 1 200px" }}>Search questions<input id={`${id}-q`} value={search} maxLength={200} onChange={(e) => setSearch(e.target.value)} /></label>
          <label htmlFor={`${id}-cat`} style={field}>Category
            <select id={`${id}-cat`} value={category} onChange={(e) => { setOffset(0); setCategory(e.target.value); }}>
              <option value="">All</option>
              {bank.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </label>
          <button type="submit" className="btn secondary small">Search</button>
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
            <input type="checkbox" checked={archived} onChange={(e) => { setOffset(0); setArchived(e.target.checked); }} /> Show archived
          </label>
        </form>
        {adding === "question"
          ? <QuestionEditor catalogue={bank} onCancel={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />
          : <div className="actions"><button type="button" className="btn small" onClick={() => setAdding("question")}>Add question</button></div>}
        {bank.items.length === 0 ? <p className="muted" style={small}>No questions match.</p> : (
          <ul aria-label="Questions" style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
            {bank.items.map((q) => (
              <li key={q.id} className="action-card" style={{ gap: 4 }}>
                <span style={{ overflowWrap: "anywhere" }}>{q.text}</span>
                <span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
                  {q.category_label} · {q.format_label}{q.evaluation_criteria && <> · Look for: {q.evaluation_criteria}</>}{q.expected_answer && <> · Expected: {q.expected_answer}</>}{!q.active && <> · Archived</>}
                </span>
                <div className="actions" style={{ flexWrap: "wrap" }}>
                  <button type="button" className="btn secondary small" aria-expanded={editing === q.id} onClick={() => setEditing((e) => (e === q.id ? null : q.id))}>
                    Edit<span className="visually-hidden"> {q.text}</span>
                  </button>
                  <button type="button" className="btn secondary small" onClick={() => void patch(`${QUESTIONS_URL}/${encodeURIComponent(q.id)}`, { active: !q.active })}>
                    {q.active ? "Archive" : "Restore"}<span className="visually-hidden"> {q.text}</span>
                  </button>
                </div>
                {editing === q.id && <QuestionEditor catalogue={bank} question={q} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
              </li>
            ))}
          </ul>
        )}
        {bank.total > PAGE && (
          <div className="actions">
            <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Previous</button>
            <span className="muted" style={{ fontSize: 13 }}>{offset + 1}–{Math.min(offset + PAGE, bank.total)} of {bank.total}</span>
            <button type="button" className="btn secondary small" disabled={offset + PAGE >= bank.total} onClick={() => setOffset((o) => o + PAGE)}>Next</button>
          </div>
        )}
      </section>

      <section className="action-card wide" aria-labelledby={`${id}-templates`}>
        <h3 id={`${id}-templates`} style={{ margin: 0 }}>Form templates</h3>
        <p className="muted" style={small}>A requirement&apos;s form starts from a template and can then be tailored.</p>
        {adding === "template"
          ? <TemplateEditor catalogue={templates} onCancel={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />
          : <div className="actions"><button type="button" className="btn small" onClick={() => setAdding("template")}>New template</button></div>}
        <ul aria-label="Templates" style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
          {templates.items.map((t) => (
            <li key={t.id} className="action-card" style={{ gap: 4 }}>
              <span style={{ overflowWrap: "anywhere" }}><strong>{t.name}</strong>{t.is_default && <span className="badge" style={{ marginLeft: 6 }}>Default</span>}{t.archived && <span className="badge" style={{ marginLeft: 6 }}>Archived</span>}</span>
              <span className="muted" style={{ fontSize: 12 }}>{t.questions.length} question{t.questions.length === 1 ? "" : "s"} · version {t.version}</span>
              <div className="actions" style={{ flexWrap: "wrap" }}>
                <button type="button" className="btn secondary small" aria-expanded={editing === t.id} onClick={() => setEditing((e) => (e === t.id ? null : t.id))}>
                  Edit<span className="visually-hidden"> {t.name}</span>
                </button>
                {!t.is_default && (
                  <button type="button" className="btn secondary small" onClick={() => void patch(`${TEMPLATES_URL}/${encodeURIComponent(t.id)}`, { archived: !t.archived })}>
                    {t.archived ? "Restore" : "Archive"}<span className="visually-hidden"> {t.name}</span>
                  </button>
                )}
              </div>
              {editing === t.id && <TemplateEditor catalogue={templates} template={t} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
