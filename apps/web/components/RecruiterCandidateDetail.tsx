"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterCalls from "@/components/RecruiterCalls";
import RecruiterCandidateApplications from "@/components/RecruiterCandidateApplications";
import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import RecruiterCandidateJourney from "@/components/RecruiterCandidateJourney";
import RecruiterCandidateNotes from "@/components/RecruiterCandidateNotes";
import RecruiterCandidateOwnership from "@/components/RecruiterCandidateOwnership";
import RecruiterCandidateTraining from "@/components/RecruiterCandidateTraining";
import RecruiterCandidateDocuments from "@/components/RecruiterCandidateDocuments";
import RecruiterCandidateResumes from "@/components/RecruiterCandidateResumes";
import RecruiterCandidateSkills from "@/components/RecruiterCandidateSkills";
import RecruiterCandidateTasks from "@/components/RecruiterCandidateTasks";
import RecruiterMessages from "@/components/RecruiterMessages";
import RecruiterRecordHistory from "@/components/RecruiterRecordHistory";
import RecruiterTimeline from "@/components/RecruiterTimeline";
import { sendRequest } from "@/lib/apiErrors";
import { telHref } from "@/lib/recruiterCalls";
import {
  AMOUNTS, CANDIDATES_PATH, CONTACT_METHODS, EMPLOYMENT_TYPES, ROW_KINDS, SHIFTS, STATUS_LABEL, WORK_MODES, candidateUrl, educationRows, experienceLabel, labelOf, packageText,
  consentSummary, rowText, type CandidateDetail, type Completeness, type RowKind,
} from "@/lib/recruiterCandidates";

/** hrc-010 (P10): the Appendix B completeness as a meter, with what is still missing. */
function CompletenessBar({ completeness }: { completeness: Completeness }) {
  const missing = completeness.items.filter((i) => !i.met);
  return (
    <div style={{ display: "grid", gap: 4, marginBottom: 12 }}>
      <span id="cand-completeness-label" style={{ fontWeight: 600 }}>Profile {completeness.percent}% complete</span>
      <div role="meter" aria-labelledby="cand-completeness-label" aria-valuemin={0} aria-valuemax={100} aria-valuenow={completeness.percent}
        style={{ height: 8, borderRadius: 4, background: "var(--border, #e5e7eb)", overflow: "hidden" }}>
        <div style={{ width: `${completeness.percent}%`, height: "100%", background: "var(--primary, #2563eb)" }} />
      </div>
      {missing.length > 0 && <span className="muted" style={{ fontSize: 13 }}>Missing: {missing.map((i) => `${i.label} (${i.weight}%)`).join(", ")}</span>}
    </div>
  );
}

// rec-009 (spec §6): one candidate -- the §8 profile, Edit (writers), Archive/Restore with a confirm, and the resume versions. hr_team reads
// only (`can_edit` false). Skills (rec-011) sit above the resumes; Applications (rec-017), Calls (rec-025) and messages (rec-026) sit
// under them; rec-027's Timeline closes the page (a call or message re-reads it).

export default function RecruiterCandidateDetail({ initial, merged }: { initial: CandidateDetail; merged?: string }) {
  const [candidate, setCandidate] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  // hrc-014: the merge screen lands here with the duplicate's code
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(merged ? { text: `${merged} was merged into this candidate.`, failed: false } : null);
  const [skillsVersion, setSkillsVersion] = useState(0); // rec-012: Apply adds skills, so the Skills card re-reads
  const [activity, setActivity] = useState(0); // rec-027: a call or message re-reads the timeline
  const touched = () => setActivity((n) => n + 1);
  const sending = useRef(false);
  useEffect(() => { // browser QA-02: the merge notice shows once -- a refresh must not repeat it
    if (merged) window.history.replaceState(window.history.state, "", window.location.pathname);
  }, [merged]);
  const archived = candidate.archived_at !== null;
  const canEdit = candidate.can_edit && !archived;

  async function reload() {
    const response = await fetch(candidateUrl(candidate.id)).catch(() => null);
    if (response?.ok) setCandidate(await response.json());
  }

  async function toggleArchive() {
    const verb = archived ? "Restore" : "Archive";
    if (!archived && !window.confirm(`Archive ${candidate.name}? They leave the candidate list until restored. Nothing is deleted.`)) return;
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    const outcome = await sendRequest(candidateUrl(candidate.id, archived ? "/restore" : "/archive"), { method: "POST" });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    setCandidate(outcome.data as unknown as CandidateDetail);
    setNotice({ text: `${verb}d.`, failed: false });
  }

  const tel = telHref(candidate.mobile);
  // hrc-001 (DEC-SCOPE-371 H2): the API leaves salary out without `candidates.compensation.view` -- no rows then, not blank ones.
  // hrc-011: each amount as entered, with its yearly rupee figure when that reads differently; Negotiable on its own row.
  const compensation: [string, React.ReactNode][] = candidate.expected_salary === undefined ? [] : [
    ...AMOUNTS.map(({ key, label }) => [label, packageText(candidate, key)] as [string, React.ReactNode]),
    ["Negotiable", candidate.salary_negotiable === true ? "Yes" : candidate.salary_negotiable === false ? "No" : null],
  ];
  const list = (values: string[] | undefined, options?: readonly { key: string; label: string }[]) =>
    (values ?? []).map((v) => (options ? labelOf(options, v) : v)).join(", ") || null;
  const derived = (candidate.employment ?? []).length > 0; // hrc-010 P4: worked out from the jobs
  const rowsOf = (kind: RowKind) => (kind === "education" ? educationRows(candidate) : candidate[kind] ?? []) as Record<string, unknown>[]; // QA-02
  const rows: [string, React.ReactNode][] = [
    ["Mobile", tel ? <a href={tel}>{candidate.mobile}<span className="visually-hidden"> (call {candidate.name})</span></a> : candidate.mobile],
    ["Email", candidate.email && <>{candidate.email}{candidate.email_verified_at ? <> <span className="badge">Verified</span></> : null}</>],
    ["Preferred contact", labelOf(CONTACT_METHODS, candidate.preferred_contact) || null], ["Location", candidate.location],
    ["Total experience", <>{experienceLabel(candidate.experience_months)}{derived && <span className="muted" style={{ fontSize: 13 }}> (from employment history)</span>}</>],
    ["Relevant experience", candidate.relevant_experience_months == null ? null : experienceLabel(candidate.relevant_experience_months)],
    ["Current company", candidate.current_company], ...compensation, ["Notice period", candidate.notice_days === null ? null : `${candidate.notice_days} days`],
    ["Preferred roles", list(candidate.preferred_roles?.length ? candidate.preferred_roles : candidate.preferred_role ? [candidate.preferred_role] : [])],
    ["Preferred locations", candidate.preferred_locations.join(", ") || null], ["Work modes", list(candidate.work_modes, WORK_MODES)],
    ["Employment types", list(candidate.employment_types, EMPLOYMENT_TYPES)], ["Shifts", list(candidate.shifts, SHIFTS)],
    ["Available from", candidate.available_from ? <LocalTime value={candidate.available_from} /> : null],
    ["Willing to relocate", candidate.willing_to_relocate === true ? "Yes" : candidate.willing_to_relocate === false ? "No" : null],
    ["Tools", list(candidate.tools)], ["Languages", list(candidate.languages)],
    ["LinkedIn", candidate.linkedin && <a href={candidate.linkedin} target="_blank" rel="noopener noreferrer nofollow" style={{ overflowWrap: "anywhere" }}>{candidate.linkedin}</a>],
    ["Source", `${candidate.source.name}${candidate.source.active ? "" : " (inactive)"}`], ["Source detail", candidate.source_detail],
    ["Campaign", candidate.utm ? Object.entries(candidate.utm).map(([key, value]) => `${key.replace("utm_", "")}: ${value}`).join(" · ") : null], // hrc-023
    ["Basis for holding", consentSummary(candidate.consent)], // hrc-035 (DEC-SCOPE-396 K2)
    ["Added", <><LocalTime value={candidate.created_at} time />{candidate.created_by ? ` by ${candidate.created_by.full_name}` : ""}</>],
    ["Last updated", <><LocalTime value={candidate.updated_at} time />{candidate.updated_by ? ` by ${candidate.updated_by.full_name}` : ""}</>],
  ];

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">{candidate.candidate_code}</div>
          <h2 style={{ overflowWrap: "anywhere" }}>{candidate.name}</h2>
          <p className="muted" style={{ margin: 0 }}>
            <span className="badge">{STATUS_LABEL[candidate.status] ?? candidate.status}</span>
            {archived && <> <span className="badge">Archived <LocalTime value={candidate.archived_at} /></span></>}
          </p>
        </div>
        {candidate.can_edit && !editing && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {!archived && <button type="button" className="btn" onClick={() => { setNotice(null); setEditing(true); }}>Edit</button>}
            {!candidate.merged_into && <button type="button" className="btn secondary" onClick={() => void toggleArchive()} disabled={busy}>{archived ? "Restore" : "Archive"}</button>}
          </div>
        )}
      </div>
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
      {/* hrc-014 D8: a merged candidate is archived for good and points at the one it was merged into */}
      {candidate.merged_into ? (
        <p className="action-card" style={{ margin: 0 }}>
          This candidate was merged into <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(candidate.merged_into.id)}`}>{candidate.merged_into.candidate_code}</Link>. Work on that record instead.
        </p>
      ) : archived && candidate.can_edit && <p className="muted" style={{ margin: 0 }}>Restore this candidate to edit them or upload a resume.</p>}
      {editing ? (
        <RecruiterCandidateForm initial={candidate} onCancel={() => setEditing(false)} onLatest={setCandidate}
          onSaved={(saved) => { setCandidate(saved); setEditing(false); setNotice({ text: "Changes saved.", failed: false }); }} />
      ) : (
        <section aria-labelledby="cand-profile-heading" className="action-card">
          <h3 id="cand-profile-heading" style={{ marginTop: 0 }}>Profile</h3>
          {candidate.completeness && <CompletenessBar completeness={candidate.completeness} />}
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "8px 16px", margin: 0 }}>
            {rows.map(([term, value]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value === null || value === undefined || value === "" ? <span className="muted">—</span> : value}</dd>
              </div>
            ))}
          </dl>
          {/* hrc-023 (W9): public website applications linked to this candidate */}
          {!!candidate.website_applications?.length && (
            <div style={{ marginTop: 16 }}>
              <h4 style={{ margin: "0 0 4px" }}>Website applications</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {candidate.website_applications.map((a) => (
                  <li key={a.tracking_code} style={{ overflowWrap: "anywhere" }}>
                    {a.job_title} · <LocalTime value={a.created_at} /> · <span className="muted">{a.tracking_code}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(Object.keys(ROW_KINDS) as RowKind[]).map((kind) => (
            <div key={kind} style={{ marginTop: 16 }}>
              <h4 style={{ margin: "0 0 4px" }}>{ROW_KINDS[kind].legend}</h4>
              {rowsOf(kind).length === 0 ? <p className="muted" style={{ margin: 0 }}>None recorded.</p> : (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {rowsOf(kind).map((row, i) => (
                    <li key={i} style={{ overflowWrap: "anywhere" }}>
                      {rowText(kind, row)}{kind === "employment" && row.end_date === null && <> <span className="badge">Current</span></>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </section>
      )}
      {/* hrc-012: who owns the candidate; a change re-reads the whole record (Change history included) */}
      {candidate.ownership && !candidate.merged_into && (
        <RecruiterCandidateOwnership candidateId={candidate.id} ownership={candidate.ownership} onSaved={(saved) => { setCandidate(saved); touched(); }} />
      )}
      {/* rec-011: re-keyed on archive/restore, so the card re-reads can_edit (an archived candidate's skills are read only). */}
      <RecruiterCandidateSkills key={`skills-${candidate.id}-${archived}-${skillsVersion}`} candidateId={candidate.id} />
      {/* rec-036: lead → IT student → trained → recruiter candidate → placed (read only). */}
      <RecruiterCandidateJourney candidateId={candidate.id} />
      {/* nehn-016: the student's training progress, read only -- the recruiter roles' (can_edit); HR's access is nehn-017's. */}
      {candidate.can_edit && <RecruiterCandidateTraining candidateId={candidate.id} />}
      <RecruiterCandidateResumes candidateId={candidate.id} resumes={candidate.resumes} canUpload={canEdit} current={candidate}
        onUploaded={() => void reload()} onApplied={() => { void reload(); setSkillsVersion((n) => n + 1); }} />
      {/* hrc-015: certificates and requested documents (readers see them; writers request, cancel and upload). */}
      <RecruiterCandidateDocuments candidateId={candidate.id} canEdit={canEdit} />
      <RecruiterCandidateApplications candidateId={candidate.id} />
      {/* rec-013: Find Candidates' Contact links here (#contact). */}
      <div id="contact" style={{ display: "grid", gap: 16, scrollMarginTop: 16 }}>
        {/* rec-025: re-keyed on archive/restore, so Log call and each call's Edit follow the candidate's state. */}
        <RecruiterCalls key={`${candidate.id}-${archived}`} party={{ kind: "candidate", candidateId: candidate.id }} canWrite={canEdit} onChanged={touched} />
        {/* rec-026: re-keyed on archive/restore and on an edit of the mobile or email, so the buttons follow the candidate. */}
        <RecruiterMessages key={`messages-${candidate.id}-${archived}-${candidate.whatsapp_to}-${candidate.email}`} canWrite={canEdit} onChanged={touched}
          source={{ kind: "candidate", party: { kind: "candidate", id: candidate.id, name: candidate.name, whatsappTo: candidate.whatsapp_to ?? null, email: candidate.email } }} />
      </div>
      {/* hrc-016: private notes and tasks (writers add on an active candidate); each write re-reads the timeline. Re-keyed on archive/restore. */}
      <RecruiterCandidateNotes key={`notes-${candidate.id}-${archived}`} candidateId={candidate.id} canAdd={canEdit} onAdded={touched} />
      <RecruiterCandidateTasks key={`tasks-${candidate.id}-${archived}`} candidateId={candidate.id} canAdd={canEdit} onChanged={touched} />
      <RecruiterTimeline party={{ kind: "candidate", id: candidate.id }} version={activity} />
      {/* hrc-004: who changed what, old → new (contact and salary hidden); re-read after every save. */}
      {/* hrc-012 QA-01: `activity` too -- a collaborator-only ownership change leaves updated_at as it was */}
      <RecruiterRecordHistory key={`${candidate.updated_at}-${activity}`} url={candidateUrl(candidate.id, "/history")} />
    </div>
  );
}
