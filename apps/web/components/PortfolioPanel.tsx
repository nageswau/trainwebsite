"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";
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
function EntryList({ section, entries, studentId, canEdit, openSection, editing, confirmingId, onAdd, onEdit, onDelete, onFormDone, onCancel }: {
  section: string; entries: PortfolioEntry[]; studentId: string; canEdit: boolean;
  openSection: string | null; editing: PortfolioEntry | null; confirmingId: string | null;
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
                      <button type="button" className="btn secondary" onClick={() => onEdit(e)}>Edit {e.title}</button>
                      <button type="button" className="btn secondary" onClick={() => onDelete(e)}>{confirmingId === e.id ? `Confirm delete ${e.title}` : `Delete ${e.title}`}</button>
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

export default function PortfolioPanel({ data }: { data: PortfolioData }) {
  const router = useRouter();
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [editing, setEditing] = useState<PortfolioEntry | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
    setDeleteError(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/students/${data.student.id}/portfolio/entries/${entry.id}`, { method: "DELETE" });
    } catch {
      setDeleteError("The request did not complete. Check your connection and try again; your entry is kept.");
      setConfirmingId(null);
      return;
    }
    setConfirmingId(null);
    if (!response.ok && response.status !== 204) {
      const body = await response.json().catch(() => null);
      setDeleteError(typeof body?.detail === "string" ? body.detail : "Delete failed.");
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
          openSection={openSection} editing={editing} confirmingId={confirmingId}
          onAdd={openAdd} onEdit={startEdit} onDelete={deleteEntry} onFormDone={onFormDone} onCancel={closeForm}
        />
      ))}

      <div className="pf-section">
        <h4>Personal statement</h4>
        {data.personal_statement ? <p className="pf-statement">{data.personal_statement}</p> : <p className="muted">No entries yet.</p>}
      </div>
    </div>
  );
}
