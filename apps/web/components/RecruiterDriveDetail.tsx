"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import RecruiterDriveForm from "@/components/RecruiterDriveForm";
import { AddCandidate } from "@/components/RecruiterRequirementCandidates";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";
import { COMPANIES_PATH } from "@/lib/recruiterCompanies";
import { collegeText, type Drive, type DriveCandidates, driveUrl, formOf, funnelSteps, isDrive, isDriveCandidates, PAGE } from "@/lib/recruiterDrives";
import { REQUIREMENTS_PATH } from "@/lib/recruiterRequirements";

type Notice = { text: string; failed: boolean } | null;

/** The applications tagged with the drive (DR9), read on open and after each add. */
function DriveCandidateList({ driveId, version }: { driveId: string; version: number }) {
  const [data, setData] = useState<DriveCandidates | null>(null);
  const [failed, setFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(`${driveUrl(driveId)}/candidates?limit=${PAGE}&offset=${offset}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isDriveCandidates(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [driveId, version, offset]);

  if (failed) return <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the drive&apos;s candidates.</p>;
  if (!data) return <p className="muted" style={{ margin: 0 }}>Loading candidates…</p>;
  if (!data.items.length) return <p className="muted" style={{ margin: 0 }}>No candidates added through this drive yet.</p>;
  return (
    <>
      {/* QA29-03: stacked items (rec-017's phone-width pattern), not a table that scrolls sideways */}
      <ul aria-label="Candidates from this drive" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {data.items.map((a) => (
          <li key={a.application_id} style={{ borderTop: "1px solid var(--line)", paddingTop: 8, display: "grid", gap: 2, overflowWrap: "anywhere" }}>
            <span><Link href={`${CANDIDATES_PATH}/${encodeURIComponent(a.candidate.id)}`} style={LINK_STYLE}>{a.candidate.name}</Link> <span className="muted">{a.candidate.code}</span></span>
            <span style={{ fontSize: 14 }}>
              <Link href={`${REQUIREMENTS_PATH}/${encodeURIComponent(a.requirement.id)}`} style={LINK_STYLE}>{a.requirement.title}</Link> · {a.status_label}
            </span>
          </li>
        ))}
      </ul>
      {data.total > PAGE && (
        <nav aria-label="Candidate pages" className="actions" style={{ gap: 8, alignItems: "center" }}>
          <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
          <span className="muted">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
          <button type="button" className="btn secondary small" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
        </nav>
      )}
    </>
  );
}

/** rec-029: one drive -- its §21 fields, the funnel (Appendix B C2-C7), its requirements and the candidates added through it. Writers
 *  edit it and add candidates to an open requirement with the drive tag; everyone else reads. */
export default function RecruiterDriveDetail({ initial }: { initial: Drive }) {
  const [drive, setDrive] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [version, setVersion] = useState(0);

  const reload = useCallback(async () => {
    setVersion((v) => v + 1);
    const response = await fetch(driveUrl(drive.id)).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    if (isDrive(body)) setDrive(body);
  }, [drive.id]);

  const writable = drive.can_edit;
  const facts: [string, string][] = [
    ["College", collegeText(drive.college)], ["Date", formatCalendarDate(drive.drive_date)], ["Job role", drive.job_role],
    ["Vacancies", String(drive.vacancies)], ["Eligibility", drive.eligibility ?? "—"],
  ];

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Campus drive · {drive.code}</div>
          <h2 style={{ overflowWrap: "anywhere" }}>{drive.job_role} at {drive.college.name}</h2>
          <p className="muted" style={{ margin: 0 }}>
            <Link href={`${COMPANIES_PATH}/${encodeURIComponent(drive.company.id)}`} style={LINK_STYLE}>{drive.company.name}</Link> · <span className="badge">{drive.status_label}</span>
          </p>
        </div>
        {writable && !editing && <button type="button" className="btn secondary" onClick={() => { setEditing(true); setNotice(null); }}>Edit drive</button>}
      </div>
      {notice && <p role={notice.failed ? "alert" : "status"} className={notice.failed ? "form-error" : "muted"} style={{ margin: 0 }}>{notice.text}</p>}
      {editing ? (
        <RecruiterDriveForm initial={formOf(drive)} driveId={drive.id} onCancel={() => setEditing(false)}
          onSaved={(saved) => { setDrive(saved); setEditing(false); setNotice({ text: "Drive saved.", failed: false }); }} />
      ) : (
        <section className="action-card" aria-labelledby="drive-details" style={{ gap: 8 }}>
          <h3 id="drive-details" style={{ margin: 0 }}>Details</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "minmax(7rem, max-content) 1fr", gap: "6px 12px", margin: 0 }}>
            {facts.map(([term, value]) => (
              <div key={term} style={{ display: "contents" }}>
                <dt className="muted">{term}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="action-card" aria-labelledby="drive-funnel" style={{ gap: 8 }}>
        <h3 id="drive-funnel" style={{ margin: 0 }}>Funnel</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          Registered and attended are entered by the recruiter. The rest count the candidates added through this drive ({drive.funnel.tagged}).
        </p>
        <ol aria-label="Drive funnel" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(7.5rem, 1fr))" }}>
          {funnelSteps(drive.funnel).map(([label, count]) => (
            <li key={label} style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "8px 10px", display: "grid" }}>
              <span className="muted" style={{ fontSize: 13 }}>{label}</span>
              <strong style={{ fontSize: 22 }}>{count}</strong>
            </li>
          ))}
        </ol>
      </section>

      <section className="action-card" aria-labelledby="drive-requirements" style={{ gap: 8 }}>
        <h3 id="drive-requirements" style={{ margin: 0 }}>Job requirements</h3>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
          {drive.requirements.map((r) => (
            <li key={r.id} style={{ display: "grid", gap: 8 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
                <Link href={`${REQUIREMENTS_PATH}/${encodeURIComponent(r.id)}`} style={LINK_STYLE}>{r.title}{r.code ? ` (${r.code})` : ""}</Link>
                {!r.open && <span className="badge">Closed</span>}
                {writable && r.open && adding !== r.id && (
                  <button type="button" className="btn secondary small" aria-label={`Add candidate to ${r.title}`} onClick={() => { setAdding(r.id); setNotice(null); }}>
                    + Add candidate
                  </button>
                )}
              </div>
              {adding === r.id && (
                <AddCandidate requirementId={r.id} statuses={drive.statuses} driveId={drive.id} label={`Add candidate to ${r.title}`}
                  onCancel={() => setAdding(null)}
                  onAdded={() => { setAdding(null); setNotice({ text: "Candidate added through this drive.", failed: false }); void reload(); }} />
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="action-card" aria-labelledby="drive-candidates" style={{ gap: 8 }}>
        <h3 id="drive-candidates" style={{ margin: 0 }}>Candidates from this drive</h3>
        <DriveCandidateList driveId={drive.id} version={version} />
      </section>
    </div>
  );
}
