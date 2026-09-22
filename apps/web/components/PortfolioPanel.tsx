"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import { formatDate } from "@/lib/formatDate";
import type { PortfolioData, PortfolioEntry } from "@/lib/portfolio";

// ENH-012 -- Digital Portfolio: docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md.
// Client Component (like SchoolTransferRequestForm.tsx) because it owns interactive state -- which
// section's Add/Edit form is open, and the Delete confirm step -- even though its data arrives already
// fetched from the server (loadPortfolio, called by the pages in Task 10). No optimistic UI: every
// mutation waits for a confirmed response, then calls router.refresh() to re-pull server data, matching
// this codebase's established pattern (spec §3.8).
//
// loadPortfolio and the PortfolioData/PortfolioEntry types live in lib/portfolio.ts, not here: this file
// has "use client", and lib/portfolio.ts's loadPortfolio calls serverApi (which imports next/headers).
// A "use client" module that reaches next/headers breaks the production build -- tests/lib/clientBoundary.test.ts
// guards against exactly this (see its own comment: ENH-005 hit it first). The two types below are
// re-exported type-only, which is erased at compile time and carries no runtime import, so it stays clear
// of that boundary while keeping `import PortfolioPanel, { type PortfolioData } from "@/components/PortfolioPanel"`
// working for callers such as this file's own tests.
export type { PortfolioData, PortfolioEntry };

const SECTION_LABELS: Record<string, string> = {
  project: "Projects", internship: "Internships", competition: "Competitions", sport: "Sports",
  leadership: "Leadership", volunteering: "Volunteering", extracurricular: "Extracurriculars",
  award: "Awards", certification: "Certifications", skill: "Skills",
};

function singular(section: string): string {
  return (SECTION_LABELS[section] ?? section).toLowerCase().replace(/s$/, "");
}

// Hoisted out of PortfolioPanel (unlike this task's source draft, which nested it): a component defined
// inside another component's render body gets a new function identity every render, so React treats it as
// a different type each time and remounts its whole subtree -- including any *other* section's open
// add/edit form -- on every state change anywhere in the panel (e.g. clicking Delete once on one entry
// would wipe a draft being typed into an unrelated section's open form). Taking the shared state as props
// instead avoids that.
function EntryList({ section, entries, studentId, canEdit, openSection, editing, confirmingId, deleteBusy, onAdd, onEdit, onDelete, onFormDone, onCancel }: {
  section: string; entries: PortfolioEntry[]; studentId: string; canEdit: boolean;
  openSection: string | null; editing: PortfolioEntry | null; confirmingId: string | null; deleteBusy: boolean;
  onAdd: (section: string) => void; onEdit: (entry: PortfolioEntry) => void; onDelete: (entry: PortfolioEntry) => void;
  onFormDone: () => void; onCancel: () => void;
}) {
  const formOpenHere = openSection === section && !editing;
  return (
    <div className="pf-section">
      <h4>{SECTION_LABELS[section] ?? section}</h4>
      {entries.length === 0 ? (
        <p className="muted">No entries yet.</p>
      ) : (
        <ul className="pf-entry-list">
          {entries.map((e) => (
            <li className="pf-entry" key={e.id}>
              {editing?.id === e.id ? (
                <PortfolioEntryForm studentId={studentId} section={e.section} entryId={e.id} initial={{ title: e.title, description: e.description, organization: e.organization, date_from: e.date_from, date_to: e.date_to }} onDone={onFormDone} onCancel={onCancel} />
              ) : (
                <>
                  <strong>{e.title}</strong>
                  {e.organization && <span className="pf-entry-org"> — {e.organization}</span>}
                  {e.date_from && <span className="pf-entry-date"> ({formatDate(e.date_from)}{e.date_to ? ` – ${formatDate(e.date_to)}` : ""})</span>}
                  {e.description && <p className="pf-entry-desc">{e.description}</p>}
                  {canEdit && (
                    <div className="pf-entry-actions">
                      <button type="button" className="btn secondary" disabled={deleteBusy} onClick={() => onEdit(e)}>Edit {e.title}</button>
                      <button id={`pf-delete-btn-${e.id}`} type="button" className="btn secondary" disabled={deleteBusy} onClick={() => onDelete(e)}>{confirmingId === e.id ? `Confirm delete ${e.title}` : `Delete ${e.title}`}</button>
                    </div>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && !formOpenHere && (
        <button type="button" className="btn secondary pf-add-btn" onClick={() => onAdd(section)}>Add {singular(section)}</button>
      )}
      {formOpenHere && <PortfolioEntryForm studentId={studentId} section={section} onDone={onFormDone} onCancel={onCancel} />}
    </div>
  );
}

// Extracted from PortfolioPanel's render body for the same reason EntryList is hoisted above: a
// function defined inline gets a new identity every render and would remount on unrelated state
// changes. Same interaction shape as PortfolioEntryForm.tsx (busy/inFlight guard, raw fetch(), no
// optimistic UI, refocus on error) but small enough (one textarea, one PATCH) that a full second form
// component would be overkill -- inlined here instead (Task 1).
function PersonalStatementSection({ studentId, statement, canEdit, onDone }: {
  studentId: string; statement: string | null; canEdit: boolean; onDone: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(statement ?? "");
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);
  const inFlight = useRef(false);

  function startEdit() {
    setValue(statement ?? "");
    setAlert(null);
    setEditing(true);
  }

  function cancel() {
    setAlert(null);
    setEditing(false);
  }

  async function save() {
    if (busy || inFlight.current) return;
    setAlert(null);
    inFlight.current = true;
    setBusy(true);
    const body = { personal_statement: value.trim() || null };
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/students/${studentId}/portfolio/personal-statement`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
    } catch {
      inFlight.current = false;
      setBusy(false);
      setAlert(NOT_COMPLETED);
      refocus("pf-statement-save-btn");
      return;
    }
    const responseBody = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (!response.ok) {
      setAlert(detailMessage(responseBody?.detail));
      refocus("pf-statement-save-btn");
      return;
    }
    setEditing(false);
    onDone();
  }

  return (
    <div className="pf-section">
      <h4>Personal statement</h4>
      {editing ? (
        <div className="form">
          <div className="field">
            <label htmlFor="pf-statement-textarea">Personal statement</label>
            <textarea id="pf-statement-textarea" className="search" rows={5} maxLength={4000} value={value} disabled={busy} onChange={(e) => setValue(e.target.value)} />
          </div>
          <button id="pf-statement-save-btn" type="button" className="btn" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn secondary" disabled={busy} onClick={cancel}>Cancel</button>
          {alert && <div role="alert" className="form-error">{alert}</div>}
        </div>
      ) : (
        <>
          {statement ? <p className="pf-statement">{statement}</p> : <p className="muted">No entries yet.</p>}
          {canEdit && <button type="button" className="btn secondary" onClick={startEdit}>{statement ? "Edit statement" : "Add statement"}</button>}
        </>
      )}
    </div>
  );
}

export default function PortfolioPanel({ data }: { data: PortfolioData }) {
  const router = useRouter();
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [editing, setEditing] = useState<PortfolioEntry | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const deleteInFlight = useRef(false);

  function closeForm() {
    setOpenSection(null);
    setEditing(null);
  }

  function onFormDone() {
    closeForm();
    router.refresh();
  }

  async function deleteEntry(entry: PortfolioEntry) {
    if (confirmingId !== entry.id) {
      setConfirmingId(entry.id);
      return;
    }
    // Guard a fast double-click on "Confirm delete": without this, the second click's DELETE races the
    // first, lands after the entry is already gone, and its 404 would incorrectly surface to a user
    // whose delete actually worked (matching PortfolioEntryForm.tsx's own busy/inFlight submit guard).
    if (deleteBusy || deleteInFlight.current) return;
    setDeleteError(null);
    deleteInFlight.current = true;
    setDeleteBusy(true);
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/students/${data.student.id}/portfolio/entries/${entry.id}`, { method: "DELETE" });
    } catch {
      deleteInFlight.current = false;
      setDeleteBusy(false);
      setConfirmingId(null);
      setDeleteError("The request did not complete. Check your connection and try again; your entry is kept.");
      refocus(`pf-delete-btn-${entry.id}`);
      return;
    }
    deleteInFlight.current = false;
    setDeleteBusy(false);
    setConfirmingId(null);
    if (!response.ok && response.status !== 204) {
      const body = await response.json().catch(() => null);
      setDeleteError(typeof body?.detail === "string" ? body.detail : "Delete failed.");
      refocus(`pf-delete-btn-${entry.id}`);
      return;
    }
    router.refresh();
  }

  function openAdd(section: string) {
    setOpenSection(section);
    setEditing(null);
  }

  function startEdit(entry: PortfolioEntry) {
    setEditing(entry);
    setOpenSection(null);
  }

  return (
    <div className="card pf-panel">
      <h3>Digital Portfolio</h3>
      <div className="pf-meter" role="progressbar" aria-valuenow={data.completion_percentage} aria-valuemin={0} aria-valuemax={100} aria-label="Portfolio completion">
        <div className="pf-meter-fill" style={{ width: `${data.completion_percentage}%` }} />
      </div>
      <p className="pf-meter-label">{data.completion_percentage}% complete</p>
      {deleteError && <div role="alert" className="form-error">{deleteError}</div>}

      <div className="pf-section">
        <h4>Profile</h4>
        <p>{data.profile_complete ? "Profile complete" : "Profile incomplete"}</p>
      </div>
      <div className="pf-section">
        <h4>Academic achievements</h4>
        {data.academic_achievements.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.academic_achievements.map((r) => <li className="pf-entry" key={r.id}>{r.subject} — {r.term}{r.grade ? ` (${r.grade})` : ""}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Psychometric report</h4>
        {data.psychometric_report.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.psychometric_report.map((r) => <li className="pf-entry" key={r.id}>{r.assessment_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Career guidance</h4>
        {data.career_guidance.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.career_guidance.map((r) => <li className="pf-entry" key={r.id}>{r.record_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Languages</h4>
        {data.languages.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.languages.map((r) => <li className="pf-entry" key={r.id}>{r.language}{r.level ? ` — ${r.level}` : ""}</li>)}</ul>
        )}
      </div>

      {Object.keys(data.entries).sort().map((section) => (
        <EntryList
          key={section} section={section} entries={data.entries[section]} studentId={data.student.id} canEdit={data.can_edit}
          openSection={openSection} editing={editing} confirmingId={confirmingId} deleteBusy={deleteBusy}
          onAdd={openAdd} onEdit={startEdit} onDelete={deleteEntry} onFormDone={onFormDone} onCancel={closeForm}
        />
      ))}

      <PersonalStatementSection studentId={data.student.id} statement={data.personal_statement} canEdit={data.can_edit} onDone={() => router.refresh()} />
    </div>
  );
}
