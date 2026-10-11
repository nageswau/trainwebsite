"use client";
import { type ReactNode, useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { type CandidateJourney, candidateJourneyUrl, isCandidateJourney, statusLabel } from "@/lib/candidateJourney";
import { formatCalendarDate } from "@/lib/formatDate";
import { SOURCE_LABEL } from "@/lib/telecallerCatalogue";

const NOT_YET = <span className="muted">Not yet</span>;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** rec-036 (CI7, AC2): EVID-018 §27 -- Lead → IT student → Trained → Recruiter candidate → Placed, each stage with its dates. Read only;
 *  the lead shows its code, source and dates, never its contact details. */
export default function RecruiterCandidateJourney({ candidateId }: { candidateId: string }) {
  const [journey, setJourney] = useState<CandidateJourney | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const headingId = `${useId()}-journey`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(candidateJourneyUrl(candidateId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isCandidateJourney(body) ? setJourney(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Journey</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the journey.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : journey === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading journey…</p>
      ) : (
        <ol aria-label="Candidate journey" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {stages(journey).map(([name, body]) => (
            <li key={name} aria-label={name} className="action-card" style={{ listStyle: "none", gap: 4 }}>
              <strong>{name}</strong>
              <div style={{ fontSize: 14, overflowWrap: "anywhere", display: "grid", gap: 2 }}>{body}</div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function stages(j: CandidateJourney): [string, ReactNode][] {
  const external = j.lead === null && j.enrolments.length === 0 && j.certificates.length === 0 && j.candidate.opted_in_at === null;
  return [
    ["Lead", j.lead ? (
      <span>{j.lead.lead_code} · {SOURCE_LABEL[j.lead.source] ?? j.lead.source} · enquired <LocalTime value={j.lead.created_at} />
        {j.lead.converted_at && <> · converted <LocalTime value={j.lead.converted_at} /></>}</span>
    ) : <span className="muted">No linked lead</span>],
    ["IT student", j.enrolments.length ? j.enrolments.map((e) => (
      <span key={`${e.program}-${e.batch}`}>{e.program} ({e.batch}) · enrolled {formatCalendarDate(e.enrolled_on)} · {statusLabel(e.status)}</span>
    )) : external ? <span className="muted">Not an EduSphere IT student</span> : NOT_YET],
    ["Trained", j.certificates.length ? j.certificates.map((c) => (
      <span key={c.certificate_no}>{c.program} · certificate {c.certificate_no} · issued {formatCalendarDate(c.issued_on)}</span>
    )) : NOT_YET],
    ["Recruiter candidate", <>
      <span>Added <LocalTime value={j.candidate.added_at} />{j.candidate.opted_in_at && <> · joined the placement pool <LocalTime value={j.candidate.opted_in_at} /></>}</span>
      <span>{j.applications.count ? <>{plural(j.applications.count, "application")} · first <LocalTime value={j.applications.first_at} /></> : <span className="muted">No applications yet</span>}</span>
    </>],
    ["Placed", j.placements.length ? j.placements.map((p, i) => (
      <span key={i}>{p.company}{p.position ? ` · ${p.position}` : ""} · joined {p.joined_on ? formatCalendarDate(p.joined_on) : "—"}</span>
    )) : NOT_YET],
  ];
}
