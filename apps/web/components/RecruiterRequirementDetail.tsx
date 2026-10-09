"use client";
import Link from "next/link";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import RecruiterRequirementForm from "@/components/RecruiterRequirementForm";
import RecruiterRequirementCandidates from "@/components/RecruiterRequirementCandidates";
import RecruiterRequirementJd from "@/components/RecruiterRequirementJd";
import RecruiterRequirementMatches from "@/components/RecruiterRequirementMatches";
import RecruiterShares from "@/components/RecruiterShares";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import type { PickOption } from "@/lib/lookups";
import { COMPANIES_PATH, personName, recruiterSearch } from "@/lib/recruiterCompanies";
import type { Jd } from "@/lib/recruiterJd";
import {
  DEADLINE_LABEL,
  experienceText,
  isRequirementBody,
  label,
  type Requirement,
  REQUIREMENTS_PATH,
  REQUIREMENTS_URL,
  salaryText,
} from "@/lib/recruiterRequirements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-007 (spec §6): one requirement. Actions render from `permissions` and `allowed_statuses` only -- the server enforces every rule.
// Every write re-renders from the requirement the API returns (no refetch). The JD section is rec-008's, Candidates is rec-017's,
// Matching candidates is rec-016's (a shortlist there re-reads Candidates); the Interviews tab arrives with rec-020.
type Changed = (r: Requirement, notice: string) => void;

function StatusChange({ requirement, onChanged }: { requirement: Requirement; onChanged: Changed }) {
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `requirement-${requirement.id}-status-change`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!status || busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${requirement.id}/status`, "POST", { status, ...(note.trim() ? { note: note.trim() } : {}) });
    setBusy(false);
    if (outcome.ok && isRequirementBody(outcome.data)) {
      setStatus("");
      setNote("");
      onChanged(outcome.data.requirement, `Status changed to ${outcome.data.requirement.status_label}.`);
    } else setFailure(outcome.ok ? "Unable to change the status." : outcome.message);
  }

  return (
    <section className="action-card wide" aria-labelledby={id}>
      <h3 id={id}>Change status</h3>
      <form className="form" onSubmit={submit} aria-busy={busy}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${id}-to`}>New status</label>
            <select id={`${id}-to`} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Choose a status</option>
              {requirement.allowed_statuses.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${id}-note`}>Note (optional)</label>
            <input id={`${id}-note`} type="text" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <div className="actions">
          <button type="submit" className="btn small" disabled={!status || busy}>
            {busy ? "Saving…" : "Change status"}
          </button>
        </div>
      </form>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}

function Reassign({ requirement, onChanged }: { requirement: Requirement; onChanged: Changed }) {
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const assignee = requirement.assigned_recruiter?.id ?? null;
  const search = useMemo(() => recruiterSearch(assignee), [assignee]);
  const triggerId = `requirement-${requirement.id}-reassign`;

  async function reassign() {
    if (!picked) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${requirement.id}/assign`, "POST", { recruiter_user_id: picked.id });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isRequirementBody(outcome.data)) {
      setPicked(null);
      onChanged(outcome.data.requirement, `Requirement assigned to ${picked.label}.`);
    } else setFailure(outcome.ok ? "Unable to reassign this requirement." : outcome.message);
  }

  return (
    <section className="action-card wide" aria-labelledby={`requirement-${requirement.id}-assignment`}>
      <h3 id={`requirement-${requirement.id}-assignment`}>Assignment</h3>
      <p style={{ margin: 0 }}>{requirement.assigned_recruiter ? `Assigned to ${personName(requirement.assigned_recruiter)}.` : "Not assigned to a recruiter yet."}</p>
      <SearchableSelect
        key={assignee ?? "none"}
        label={requirement.assigned_recruiter ? "Reassign to" : "Assign to"}
        noun="recruiter"
        search={search}
        onChange={(option) => {
          setPicked(option);
          setConfirming(false);
        }}
      />
      <div>
        <button id={triggerId} type="button" className="btn secondary small" disabled={!picked || busy} onClick={() => setConfirming(true)}>
          {requirement.assigned_recruiter ? "Reassign" : "Assign"}
        </button>
      </div>
      {confirming && picked && (
        <BdmConfirm label="Confirm assignment" confirmText="Yes, assign" busyText="Assigning…" busy={busy} onConfirm={() => void reassign()} onCancel={() => { setConfirming(false); focus(triggerId); }}>
          Assign {requirement.code} to {picked.label}?
        </BdmConfirm>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}

function skillItems(requirement: Requirement, kind: "required" | "preferred"): ReactNode {
  const items = requirement.skills.filter((s) => s.kind === kind);
  if (items.length === 0) return "—";
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {items.map((s) => (
        <li key={s.id}>
          {s.name}
          {!s.matched && (
            <>
              {" "}
              <span className="status pending" title="Not in the Skills Master: kept as typed">
                Not in Skills Master
              </span>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function RecruiterRequirementDetail({ initial, initialJd, created = false }: { initial: Requirement; initialJd: Jd | null; created?: boolean }) {
  const [requirement, setRequirement] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Requirement ${initial.code} created.` : null);
  const [shortlists, setShortlists] = useState(0);
  const [shares, setShares] = useState(0); // rec-019: a share from either section re-reads the board and the Shared profiles list
  const focus = useFocusAfterRender();
  useEffect(() => {
    if (created) window.history.replaceState(null, "", `${REQUIREMENTS_PATH}/${initial.id}`);
  }, [created, initial.id]);
  const r = requirement;
  const p = r.permissions;
  const editId = `requirement-${r.id}-edit`;
  const statusId = `requirement-${r.id}-notice`;
  const showEditor = editing && p.can_edit;
  const changed: Changed = (next, text) => {
    setRequirement(next);
    setNotice(text);
    focus(statusId);
  };
  const closeEditor = () => {
    setEditing(false);
    focus(editId);
  };

  const rows: [string, ReactNode][] = [
    ["Company", <Link key="company" href={`${COMPANIES_PATH}/${r.company.id}`} style={LINK_STYLE}>{r.company.name} ({r.company.code})</Link>],
    ["Department", display(r.department)],
    ["Job category", display(r.job_category?.name)],
    ["Number of vacancies", r.vacancies == null ? "—" : `${r.vacancies}${r.joined_count ? ` (${r.joined_count} joined)` : ""}`],
    ["Qualification", display(r.qualification)],
    ["Experience", experienceText(r.experience_min_months, r.experience_max_months)],
    ["Salary range", salaryText(r.salary_min, r.salary_max)],
    ["Job location", display(r.location)],
    ["Work mode", label(r.work_mode)],
    ["Shift", label(r.shift)],
    ["Employment type", label(r.employment_type)],
    ["Joining requirement", display(r.joining_requirement)],
    ["Application deadline", r.closes_on ? formatCalendarDate(r.closes_on) : "—"],
    ["Requirement date", r.requirement_date ? formatCalendarDate(r.requirement_date) : "—"],
    ["Priority", label(r.priority)],
    ["Assigned recruiter", personName(r.assigned_recruiter)],
    ["Required skills", skillItems(r, "required")],
    ["Preferred skills", skillItems(r, "preferred")],
    ["Job description", multiline(r.description || null)],
    ["Added by", r.created_by ? <>{r.created_by.full_name} on <LocalTime value={r.created_at} /></> : "—"],
  ];

  return (
    <>
      <div className="portal-title" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="eyebrow">{r.code}</div>
          <h2>
            {r.title} <span className="badge">{r.status_label}</span>{" "}
            {r.deadline_state && <span className={r.deadline_state === "expired" ? "status error" : "status pending"}>{DEADLINE_LABEL[r.deadline_state]}</span>}
          </h2>
          <p style={{ margin: 0 }}>
            <Link href={REQUIREMENTS_PATH} style={LINK_STYLE}>
              Back to job requirements
            </Link>
          </p>
        </div>
        <div className="actions">
          {p.can_edit && !showEditor && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <RecruiterRequirementForm
            mode="edit"
            requirement={r}
            onSaved={(next, saved) => {
              changed(next, saved ? "Changes saved." : "No changes to save.");
              closeEditor();
            }}
            onCancel={closeEditor}
          />
        </section>
      ) : (
        <section className="action-card wide" aria-label="Details">
          <h3>Details</h3>
          <DetailList rows={rows} />
        </section>
      )}
      <RecruiterRequirementJd requirement={r} initial={initialJd} onRequirementChanged={changed} />
      {p.can_change_status && !showEditor && <StatusChange requirement={r} onChanged={changed} />}
      {p.can_reassign && <Reassign requirement={r} onChanged={changed} />}
      <section className="action-card wide" aria-labelledby={`requirement-${r.id}-history`}>
        <h3 id={`requirement-${r.id}-history`}>Status history</h3>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {r.status_history.map((h, i) => (
            <li key={`${h.created_at}-${i}`}>
              <LocalTime value={h.created_at} time />: {h.from_label ? `${h.from_label} → ${h.to_label}` : `Started as ${h.to_label}`}
              {h.note && <> — {h.note}</>} <span className="muted">by {h.changed_by ? h.changed_by.full_name : "the system"}</span>
            </li>
          ))}
        </ul>
      </section>
      {/* rec-017: after the requirement's own status controls and history, so its two "Change status" forms never sit side by side (QA-02). */}
      <RecruiterRequirementCandidates requirementId={r.id} requirementLabel={r.title} companyId={r.company.id} refreshKey={shortlists + shares}
        onShared={() => setShares((n) => n + 1)} />
      {p.can_view_matches && (
        <RecruiterRequirementMatches requirementId={r.id} requirementLabel={r.title} companyId={r.company.id} version={r.updated_at}
          onRequirementChanged={setRequirement} onShortlisted={() => setShortlists((n) => n + 1)} onShared={() => setShares((n) => n + 1)} />
      )}
      <RecruiterShares source={{ kind: "requirement", requirementId: r.id }} refreshKey={shares} />
    </>
  );
}
