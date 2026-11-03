import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ItStudentProfileForm from "@/components/ItStudentProfileForm";
import PortalShell from "@/components/PortalShell";
import StudentResumeCard from "@/components/StudentResumeCard";
import { ApiError, serverApi } from "@/lib/api";
import { formatRiskDate, riskReasonLabels, studentRiskUrl, type RiskFlag } from "@/lib/itAtRisk";
import { itEnrollmentsUrl, itStudentProfileUrl, MY_IT_PROFILE_URL, type ItStudentProfileResponse } from "@/lib/itStudentProfile";
import { PORTAL_NAV } from "@/lib/navigation";
import { studentResumesUrl } from "@/lib/studentResumes";
import type { User } from "@/lib/types";

const PORTALS = {
  counselor: { nav: "it/counselor", roleLabel: "Counselor", back: "/it/counselor/students", backLabel: "my students" },
  admin: { nav: "it/admin", roleLabel: "IT Administrator", back: "/it/admin/students", backLabel: "students" },
} as const;

/** itc-012 (DEC-SCOPE-345): the IT student's own record, under their Profile section (the account form stays below it). */
export async function MyItStudentProfile() {
  let data: ItStudentProfileResponse;
  try {
    data = await serverApi<ItStudentProfileResponse>(MY_IT_PROFILE_URL);
  } catch {
    return <div className="card" role="status" style={{ marginTop: 16 }}>Your details could not be loaded. Refresh the page to try again.</div>;
  }
  return (
    <section className="card" aria-labelledby="my-it-details-heading" style={{ marginTop: 16 }}>
      <h3 id="my-it-details-heading">My details</h3>
      <p className="muted">Your personal details and emergency contact. Your IT counselor and the IT Admin see and can update them too.</p>
      <ItStudentProfileForm initial={data} url={MY_IT_PROFILE_URL} />
    </section>
  );
}

/** itc-012: /it/{counselor|admin}/students/[id]/profile -- the API is the gate and the scope (a student outside the counselor's caseload
 *  is a 404, another role a 403 card), and each reader stays in their own portal. */
export default async function ItStudentProfilePage({ portal, id }: { portal: keyof typeof PORTALS; id: string }) {
  const { nav, roleLabel, back, backLabel } = PORTALS[portal];
  let user: User;
  let data: ItStudentProfileResponse;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  // QA-01: the two portals call different APIs, so an IT Admin on the counselor address (or the reverse) moves to their own first.
  const own = user.role === "it_admin" ? "admin" : user.role === "counselor" && user.division === "it" ? "counselor" : null;
  if (own && own !== portal) redirect(`/it/${own}/students/${encodeURIComponent(id)}/profile`);
  try {
    data = await serverApi<ItStudentProfileResponse>(itStudentProfileUrl(portal, id));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // a malformed id is not found, too
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={PORTAL_NAV[nav] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={back}>← Back to {backLabel}</Link></p>
        <h1>Student record: {data.student.full_name}</h1>
        {data.student.student_code && <p className="muted">Student ID {data.student.student_code}</p>}
        {/* itc-033 (DEC-SCOPE-357 C3): the student's own choice, set on their profile; staff can't change it */}
        {data.student.calls_allowed === false && (
          <p data-testid="calls-opt-out">
            <span className="badge">No phone calls</span> The student has asked not to be called. Use email or in-app messages instead.
          </p>
        )}
        <StudentRiskCard studentId={data.student.id} />
        <div className="card">
          <ItStudentProfileForm initial={data} url={itStudentProfileUrl(portal, id)} enrollmentsUrl={itEnrollmentsUrl(portal, id)} />
        </div>
        <div style={{ marginTop: 16 }}>
          <StudentResumeCard url={studentResumesUrl(portal, id)} description="Upload a resume on the student's behalf. Each upload is a new version; earlier ones are kept." />
        </div>
      </div>
    </PortalShell>
  );
}

/** itc-023 (DEC-SCOPE-352): the student's at-risk flag (open first) and its history, as of the last daily check. */
async function StudentRiskCard({ studentId }: { studentId: string }) {
  let flags: RiskFlag[];
  try {
    flags = await serverApi<RiskFlag[]>(studentRiskUrl(studentId));
  } catch {
    return <div className="card" role="status" style={{ marginBottom: 16 }}>The at-risk status could not be loaded. Refresh the page to try again.</div>;
  }
  const open = flags.find((f) => f.cleared_at === null);
  const past = flags.filter((f) => f.cleared_at !== null);
  return (
    <section className="card" aria-labelledby="student-risk-heading" style={{ marginBottom: 16 }}>
      <h3 id="student-risk-heading" style={{ fontSize: 18, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        At-risk status <span className={open ? "status error" : "status"}>{open ? "At risk" : "Not at risk"}</span>
      </h3>
      {open ? (
        <p style={{ margin: 0 }}>Flagged on {formatRiskDate(open.raised_at)} in {open.program} ({open.batch.name}): {riskReasonLabels(open).join(", ")}.</p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>Not at risk at the last daily check.</p>
      )}
      {past.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>Earlier flags ({past.length})</summary>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {past.map((f) => (
              <li key={f.id}>
                {formatRiskDate(f.raised_at)} – {formatRiskDate(f.cleared_at as string)}: {riskReasonLabels(f).join(", ")}
                {f.clear_reason === "stopped" ? " (monitoring stopped)" : " (back on track)"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
