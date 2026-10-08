"use client";

import { useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterCalls from "@/components/RecruiterCalls";
import RecruiterCandidateApplications from "@/components/RecruiterCandidateApplications";
import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import RecruiterCandidateResumes from "@/components/RecruiterCandidateResumes";
import RecruiterMessages from "@/components/RecruiterMessages";
import { sendRequest } from "@/lib/apiErrors";
import { telHref } from "@/lib/recruiterCalls";
import { STATUS_LABEL, candidateUrl, experienceLabel, type CandidateDetail } from "@/lib/recruiterCandidates";

// rec-009 (spec §6): one candidate -- the §8 profile, Edit (writers), Archive/Restore with a confirm, and the resume versions. hr_team reads
// only (`can_edit` false). Applications (rec-017), Calls (rec-025) and messages (rec-026) sit under the resumes; skills and the
// timeline arrive with rec-011 and rec-027; no empty tabs stand in.
const money = (v: string | null) => (v === null ? null : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }));

export default function RecruiterCandidateDetail({ initial }: { initial: CandidateDetail }) {
  const [candidate, setCandidate] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const sending = useRef(false);
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
  const rows: [string, React.ReactNode][] = [
    ["Mobile", tel ? <a href={tel}>{candidate.mobile}<span className="visually-hidden"> (call {candidate.name})</span></a> : candidate.mobile], ["Email", candidate.email], ["Location", candidate.location], ["Qualification", candidate.qualification],
    ["College", candidate.college], ["Passing year", candidate.passing_year], ["Total experience", experienceLabel(candidate.experience_months)],
    ["Current company", candidate.current_company], ["Current salary (per year)", money(candidate.current_salary)],
    ["Expected salary (per year)", money(candidate.expected_salary)], ["Notice period", candidate.notice_days === null ? null : `${candidate.notice_days} days`],
    ["Preferred locations", candidate.preferred_locations.join(", ") || null], ["Preferred role", candidate.preferred_role],
    ["LinkedIn", candidate.linkedin && <a href={candidate.linkedin} target="_blank" rel="noopener noreferrer nofollow" style={{ overflowWrap: "anywhere" }}>{candidate.linkedin}</a>],
    ["Source", `${candidate.source.name}${candidate.source.active ? "" : " (inactive)"}`], ["Source detail", candidate.source_detail],
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
            <button type="button" className="btn secondary" onClick={() => void toggleArchive()} disabled={busy}>{archived ? "Restore" : "Archive"}</button>
          </div>
        )}
      </div>
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
      {archived && candidate.can_edit && <p className="muted" style={{ margin: 0 }}>Restore this candidate to edit them or upload a resume.</p>}
      {editing ? (
        <RecruiterCandidateForm initial={candidate} onCancel={() => setEditing(false)}
          onSaved={(saved) => { setCandidate(saved); setEditing(false); setNotice({ text: "Changes saved.", failed: false }); }} />
      ) : (
        <section aria-labelledby="cand-profile-heading" className="action-card">
          <h3 id="cand-profile-heading" style={{ marginTop: 0 }}>Profile</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "8px 16px", margin: 0 }}>
            {rows.map(([term, value]) => (
              <div key={term}>
                <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value === null || value === undefined || value === "" ? <span className="muted">—</span> : value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      <RecruiterCandidateResumes candidateId={candidate.id} resumes={candidate.resumes} canUpload={canEdit} onUploaded={() => void reload()} />
      <RecruiterCandidateApplications candidateId={candidate.id} />
      {/* rec-025: re-keyed on archive/restore, so Log call and each call's Edit follow the candidate's state. */}
      <RecruiterCalls key={`${candidate.id}-${archived}`} party={{ kind: "candidate", candidateId: candidate.id }} canWrite={canEdit} />
      {/* rec-026: re-keyed on archive/restore and on an edit of the mobile or email, so the buttons follow the candidate. */}
      <RecruiterMessages key={`messages-${candidate.id}-${archived}-${candidate.whatsapp_to}-${candidate.email}`} canWrite={canEdit}
        source={{ kind: "candidate", party: { kind: "candidate", id: candidate.id, name: candidate.name, whatsappTo: candidate.whatsapp_to ?? null, email: candidate.email } }} />
    </div>
  );
}
