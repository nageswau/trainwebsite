"use client";

import { useEffect, useState } from "react";

import { COURSE_LEVELS, QUALIFICATION_LEVELS, STUDY_MODES, TEST_STATUSES, agencyProfileUrl, type StudentProfile } from "@/lib/studentProfile";

function qualificationText(q: StudentProfile["qualifications"][number]): string {
  const title = [QUALIFICATION_LEVELS[q.level] ?? q.level, q.qualification_name].filter(Boolean).join(" — ");
  const score = q.score === null ? null : q.score_type === "percentage" ? `${q.score}%` : `${q.score_type === "cgpa" ? "CGPA" : "Score"} ${q.score}`;
  return [title, q.institution, q.year_completed, score, q.backlogs ? `${q.backlogs} backlog${q.backlogs === 1 ? "" : "s"}` : null].filter(Boolean).join(", ");
}

function testText(t: StudentProfile["english_tests"][number]): string {
  const head = [t.test_type, t.overall_score].filter(Boolean).join(" ");
  return [head, t.status ? TEST_STATUSES[t.status] : null, t.expired ? "expired" : null, t.remarks].filter(Boolean).join(" · ");
}

// ccrm-007 (DEC-SCOPE-249 P2/P3): the student's own structured profile beside the agency record, read-only and without the passport
// (the API never sends it to an agency). Shown only for a student with a login; the agency's own fields above stay the agency's record.
export default function AgentStudentProfileCard({ studentId }: { studentId: string }) {
  const [state, setState] = useState<{ profile: StudentProfile | null } | "loading" | "failed">("loading");
  const headingId = `agent-student-profile-${studentId}`;

  useEffect(() => {
    let live = true;
    setState("loading");
    fetch(agencyProfileUrl(studentId))
      .then(async (r) => (r.ok ? ((await r.json()) as { profile: StudentProfile | null }) : Promise.reject(new Error(String(r.status)))))
      .then((data) => live && setState(data && "profile" in data ? data : "failed"))
      .catch(() => live && setState("failed"));
    return () => {
      live = false;
    };
  }, [studentId]);

  const profile = typeof state === "object" ? state.profile : null;
  const rows: [string, string | null][] = profile
    ? [
        ["Date of birth", profile.date_of_birth],
        ["Nationality", profile.nationality],
        ["City / state", [profile.city, profile.state].filter(Boolean).join(", ") || null],
        ["Work experience", profile.work_experience_months === null ? profile.work_experience_details : [`${profile.work_experience_months} months`, profile.work_experience_details].filter(Boolean).join(" — ")],
        ["Preferred countries", profile.preferred_countries.map((c) => c.name).join(", ") || null],
        ["Course or subject", profile.preferred_course],
        ["Study level", profile.preferred_level ? (COURSE_LEVELS[profile.preferred_level] ?? profile.preferred_level) : null],
        ["Intake", profile.preferred_intake],
        ["Study mode", profile.study_mode ? (STUDY_MODES[profile.study_mode] ?? profile.study_mode) : null],
        ["Budget", profile.budget_currency && (profile.budget_min || profile.budget_max) ? `${profile.budget_currency} ${[profile.budget_min, profile.budget_max].filter(Boolean).join(" – ")}` : null],
      ]
    : [];

  return (
    <section aria-labelledby={headingId} style={{ marginTop: 16 }}>
      <h5 id={headingId} style={{ fontSize: "18px", margin: "0 0 8px" }}>Student profile</h5>
      {state === "loading" && <p className="muted" role="status">Loading the student&apos;s profile…</p>}
      {state === "failed" && <p className="muted" role="status">The student&apos;s profile could not be loaded.</p>}
      {typeof state === "object" && (!profile || !profile.exists) && <p className="muted">The student&apos;s profile has not been filled in yet.</p>}
      {profile?.exists && (
        <>
          <p className="muted" style={{ fontSize: 13 }}>Kept by the student and their EduSphere counselor; read-only here.</p>
          <dl className="record-details">
            {rows.map(([label, value]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt>{label}</dt>
                <dd>{value || "—"}</dd>
              </div>
            ))}
            <div style={{ display: "contents" }}>
              <dt>Qualifications</dt>
              <dd>{profile.qualifications.length ? <ul className="list-clean" style={{ margin: 0 }}>{profile.qualifications.map((q, i) => <li key={i}>{qualificationText(q)}</li>)}</ul> : "—"}</dd>
            </div>
            <div style={{ display: "contents" }}>
              <dt>English tests</dt>
              <dd>{profile.english_tests.length ? <ul className="list-clean" style={{ margin: 0 }}>{profile.english_tests.map((t, i) => <li key={i}>{testText(t)}</li>)}</ul> : "—"}</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}
