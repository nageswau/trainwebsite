"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import RecruiterCompanyContacts from "@/components/RecruiterCompanyContacts";
import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import RecruiterCompanyPipeline from "@/components/RecruiterCompanyPipeline";
import RecruiterStageHistory from "@/components/RecruiterStageHistory";
import SearchableSelect from "@/components/SearchableSelect";
import { type Page, sendJson, sendRequest } from "@/lib/apiErrors";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import type { PickOption } from "@/lib/lookups";
import { type Company, COMPANIES_PATH, COMPANIES_URL, isCompanyBody, personName, PRIORITY_LABEL, recruiterSearch, safeLink } from "@/lib/recruiterCompanies";
import type { StageEvent } from "@/lib/recruiterPipeline";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-003 (spec §6): one company. Actions render from `permissions` only -- the server enforces every rule. Every write re-renders from
// the company the API returns (no refetch). Contacts are rec-004's section; rec-005 adds the pipeline and its history (reloaded after
// each pipeline write); follow-ups and contracts arrive with rec-024/030.
function linkOrText(url: string | null) {
  const safe = safeLink(url);
  return safe ? (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {safe}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  ) : (
    display(url)
  );
}

function Reassign({ company, onChanged }: { company: Company; onChanged: (c: Company, notice: string) => void }) {
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const assignee = company.assigned_recruiter?.id ?? null;
  const search = useMemo(() => recruiterSearch(assignee), [assignee]);
  const triggerId = `company-${company.id}-reassign`;

  async function reassign() {
    if (!picked) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${COMPANIES_URL}/${company.id}/assign`, "POST", { recruiter_user_id: picked.id });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isCompanyBody(outcome.data)) {
      setPicked(null);
      onChanged(outcome.data.company, `Company assigned to ${picked.label}.`);
    } else setFailure(outcome.ok ? "Unable to reassign this company." : outcome.message);
  }

  return (
    <section className="action-card wide" aria-labelledby={`company-${company.id}-assignment`}>
      <h3 id={`company-${company.id}-assignment`}>Assignment</h3>
      <p style={{ margin: 0 }}>{company.assigned_recruiter ? `Assigned to ${personName(company.assigned_recruiter)}.` : "Not assigned to a recruiter yet."}</p>
      <SearchableSelect
        key={assignee ?? "none"}
        label={company.assigned_recruiter ? "Reassign to" : "Assign to"}
        noun="recruiter"
        search={search}
        onChange={(option) => {
          setPicked(option);
          setConfirming(false);
        }}
      />
      <div>
        <button id={triggerId} type="button" className="btn secondary small" disabled={!picked || busy} onClick={() => setConfirming(true)}>
          {company.assigned_recruiter ? "Reassign" : "Assign"}
        </button>
      </div>
      {confirming && picked && (
        <BdmConfirm label="Confirm assignment" confirmText="Yes, assign" busyText="Assigning…" busy={busy} onConfirm={() => void reassign()} onCancel={() => { setConfirming(false); focus(triggerId); }}>
          Assign {company.code} to {picked.label}?
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

export default function RecruiterCompanyDetail({ initial, created = false, history = null }: { initial: Company; created?: boolean; history?: Page<StageEvent> | null }) {
  const [company, setCompany] = useState(initial);
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Company ${initial.code} created.` : null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  // "created" is said once: the flag leaves the address, so a refresh or a shared link doesn't repeat it (BdmOrganizationDetail's rule).
  useEffect(() => {
    if (created) window.history.replaceState(null, "", `${COMPANIES_PATH}/${initial.id}`);
  }, [created, initial.id]);
  const archiveId = `company-${company.id}-archive`;
  const editId = `company-${company.id}-edit`;
  const statusId = `company-${company.id}-status`;
  const p = company.permissions;
  const showEditor = editing && p.can_edit;
  const changed = (next: Company, text: string) => {
    setCompany(next);
    setNotice(text);
    setFailure(null);
  };
  const stageChanged = (next: Company) => {
    setCompany(next);
    setVersion((v) => v + 1); // only pipeline writes add history rows
  };
  const closeEditor = () => {
    setEditing(false);
    focus(editId);
  };

  async function act(path: "archive" | "restore") {
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(`${COMPANIES_URL}/${company.id}/${path}`, { method: "POST" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isCompanyBody(outcome.data)) {
      changed(outcome.data.company, path === "archive" ? "Company archived." : "Company restored.");
      focus(statusId);
    } else setFailure(outcome.ok ? "Unable to update this company." : outcome.message);
  }

  const rows: [string, ReactNode][] = [
    ["Industry", display(company.industry?.name)],
    ["Website", linkOrText(company.website)],
    ["LinkedIn", linkOrText(company.linkedin_url)],
    ["Company size", display(company.company_size?.name)],
    ["Number of employees", display(company.employee_count)],
    ["City", display(company.city)],
    ["State", display(company.state)],
    ["Country", display(company.country)],
    ["Head office", display(company.head_office)],
    ["Branches", multiline(company.branches)],
    ["Company description", multiline(company.description)],
    ["Lead source", display(company.lead_source?.name)],
    ["Campaign", display(company.campaign?.name)],
    ["Priority", company.priority ? PRIORITY_LABEL[company.priority] : "—"],
    ["Recruiter (account manager)", personName(company.assigned_recruiter)],
    ["Assigned BDM", personName(company.assigned_bdm, "—")],
    ["Registered by", company.owner_type === "employer_self_service" ? "The employer (self-registration)" : company.created_by ? <>{company.created_by.full_name} on <LocalTime value={company.created_at} /></> : "—"],
  ];

  return (
    <>
      <div className="portal-title" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="eyebrow">{company.code}</div>
          <h2>
            {company.name} {company.archived && <span className="badge">Archived</span>}
          </h2>
          <p style={{ margin: 0 }}>
            <Link href={COMPANIES_PATH} style={LINK_STYLE}>
              Back to companies
            </Link>
          </p>
        </div>
        <div className="actions">
          {p.can_edit && !showEditor && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
          {p.can_archive && !showEditor && (
            <button id={archiveId} type="button" className="btn secondary small" onClick={() => setConfirming(true)} disabled={busy}>
              Archive
            </button>
          )}
          {p.can_restore && (
            <button type="button" className="btn small" onClick={() => void act("restore")} disabled={busy}>
              {busy ? "Restoring…" : "Restore"}
            </button>
          )}
        </div>
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      {confirming && (
        <BdmConfirm label="Confirm archive" className="action-card" confirmText="Yes, archive" busyText="Archiving…" cancelText="Keep it" busy={busy} onConfirm={() => void act("archive")} onCancel={() => { setConfirming(false); focus(archiveId); }}>
          Archive {company.name}? It will be hidden from the list and read-only until a manager restores it.
        </BdmConfirm>
      )}
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <RecruiterCompanyForm
            mode="edit"
            company={company}
            canChooseRecruiter={false}
            onSaved={(c, saved) => {
              changed(c, saved ? "Changes saved." : "No changes to save.");
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
      {/* Re-keyed on archive/restore: the list's `can_edit` follows the company's state. */}
      <RecruiterCompanyContacts key={`${company.id}-${company.archived}`} companyId={company.id} />
      <RecruiterCompanyPipeline
        company={company}
        onChanged={(c, text) => {
          changed(c, text);
          stageChanged(c);
          focus(statusId);
        }}
        onRefreshed={stageChanged}
      />
      <RecruiterStageHistory companyId={company.id} initial={history} version={version} />
      {p.can_reassign && (
        <Reassign
          company={company}
          onChanged={(c, text) => {
            changed(c, text);
            focus(statusId);
          }}
        />
      )}
      {company.assignment_history.length > 0 && (
        <section className="action-card wide" aria-labelledby={`company-${company.id}-history`}>
          <h3 id={`company-${company.id}-history`}>Assignment history</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {company.assignment_history.map((h, i) => (
              <li key={`${h.created_at}-${i}`}>
                <LocalTime value={h.created_at} time />: {personName(h.from_user)} → {personName(h.to_user)} <span className="muted">by {h.changed_by.full_name}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
