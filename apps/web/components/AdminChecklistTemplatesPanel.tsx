"use client";

import { useCallback, useEffect, useState } from "react";
import ChecklistTemplateEditor from "@/components/ChecklistTemplateEditor";
import { detailMessage } from "@/lib/apiErrors";
import { CHECKLISTS_URL, GATE_LABELS, KIND_LABELS, scopeText, type ChecklistKind, type ChecklistSummary, type ChecklistTemplate } from "@/lib/documentChecklists";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Status = "active" | "inactive" | "all";
const STATUSES: { value: Status; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "all", label: "All" },
];
const NOTICE_ID = "checklists-notice";
const NEW_ID = "checklist-new-open";
const editId = (id: string) => `checklist-edit-${id}`;

// ccrm-018 (DEC-SCOPE-248): the Overseas Admin's document checklist templates -- filter by kind and status, create, edit (which also
// deactivates/reactivates). Nothing is seeded (§8): an empty list says so. Editing loads the full template first so the form has its
// items and the version the server will check.
export default function AdminChecklistTemplatesPanel() {
  const [kind, setKind] = useState<ChecklistKind | "">("");
  const [status, setStatus] = useState<Status>("active");
  const [items, setItems] = useState<ChecklistSummary[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [editing, setEditing] = useState<ChecklistTemplate | "new" | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [openFailure, setOpenFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focusAfter = useFocusAfterRender();

  const load = useCallback(() => {
    setLoadFailed(false);
    setItems(null);
    const query = new URLSearchParams({ status });
    if (kind) query.set("kind", kind);
    fetch(`${CHECKLISTS_URL}?${query}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: { items?: ChecklistSummary[] }) => (Array.isArray(body.items) ? setItems(body.items) : setLoadFailed(true)))
      .catch(() => setLoadFailed(true));
  }, [kind, status]);

  useEffect(load, [load]);

  async function openEditor(summary: ChecklistSummary) {
    setNotice(null);
    setOpenFailure(null);
    setOpening(summary.id);
    try {
      const res = await fetch(`${CHECKLISTS_URL}/${summary.id}`);
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(detailMessage(body?.detail, "Unable to open this template."));
      setEditing(body as ChecklistTemplate);
    } catch (e) {
      setOpenFailure(e instanceof Error ? e.message : "Unable to open this template.");
    } finally {
      setOpening(null);
    }
  }
  function saved(template: ChecklistTemplate, created: boolean) {
    setEditing(null);
    setNotice(`${created ? "Created" : "Saved"} ${template.name} (version ${template.version}).`);
    focusAfter(NOTICE_ID);
    load();
  }
  function cancel() {
    const opener = editing && editing !== "new" ? editId(editing.id) : NEW_ID;
    setEditing(null);
    focusAfter(opener);
  }

  if (editing) {
    return (
      <div className="action-card">
        <ChecklistTemplateEditor template={editing === "new" ? null : editing} onSaved={(t) => saved(t, editing === "new")} onCancel={cancel} />
      </div>
    );
  }
  return (
    <div className="action-card">
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <h3>Document checklists</h3>
        <button
          type="button"
          id={NEW_ID}
          className="btn small"
          onClick={() => {
            setNotice(null);
            setEditing("new");
          }}
        >
          New template
        </button>
      </div>
      <div id={NOTICE_ID} tabIndex={-1} className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginTop: 8 } : undefined}>
        {notice}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 12, alignItems: "end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="checklists-kind">Checklist for</label>
          <select id="checklists-kind" value={kind} onChange={(e) => setKind(e.target.value as ChecklistKind | "")}>
            <option value="">Admission and visa</option>
            {(Object.keys(KIND_LABELS) as ChecklistKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <div role="group" aria-label="Template status" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {STATUSES.map((s) => (
            <button key={s.value} type="button" className={s.value === status ? "btn small" : "btn secondary small"} aria-pressed={s.value === status} onClick={() => setStatus(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {openFailure && (
        <p className="form-error" role="alert" style={{ marginTop: 8 }}>
          {openFailure}
        </p>
      )}
      <section aria-label="Templates" style={{ marginTop: 16 }}>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">
              Unable to load checklist templates.
            </p>
            <button type="button" className="btn secondary small" onClick={load}>
              Retry
            </button>
          </>
        ) : items === null ? (
          <p className="muted" aria-busy="true">
            Loading checklist templates…
          </p>
        ) : items.length === 0 ? (
          <p className="muted">No templates here yet. A checklist applies to an application only when a template matches its country (and any university, level or intake you set).</p>
        ) : (
          <div className="grid two">
            {items.map((t) => (
              <div className="card" key={t.id} style={{ overflowWrap: "anywhere" }}>
                <span className="badge">{KIND_LABELS[t.kind]}</span> {!t.active && <span className="badge">Inactive</span>}
                <h4 style={{ marginTop: 10, fontSize: "1rem" }}>{t.name}</h4>
                <p className="muted" style={{ fontSize: 13 }}>
                  {scopeText(t)}
                </p>
                <dl className="card-stack">
                  <dt>Documents</dt>
                  <dd>{t.item_count}</dd>
                  <dt>Gate</dt>
                  <dd>{GATE_LABELS[t.gate_mode]}</dd>
                  <dt>Version</dt>
                  <dd>{t.version}</dd>
                </dl>
                <div className="actions">
                  <button type="button" id={editId(t.id)} className="btn secondary small" aria-label={`Edit ${t.name}`} disabled={opening === t.id} onClick={() => openEditor(t)}>
                    {opening === t.id ? "Opening…" : "Edit"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
