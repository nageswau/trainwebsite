import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ItStudentProfileForm from "@/components/ItStudentProfileForm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { itEnrollmentsUrl, itStudentProfileUrl, MY_IT_PROFILE_URL, type ItStudentProfileResponse } from "@/lib/itStudentProfile";
import { PORTAL_NAV } from "@/lib/navigation";
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
        <div className="card">
          <ItStudentProfileForm initial={data} url={itStudentProfileUrl(portal, id)} enrollmentsUrl={itEnrollmentsUrl(portal, id)} />
        </div>
      </div>
    </PortalShell>
  );
}
