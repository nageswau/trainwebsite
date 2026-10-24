import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import StudentProfileForm from "@/components/StudentProfileForm";
import { ApiError, publicApi, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { MY_PROFILE_URL, studentProfileUrl, type CountryOption, type StudentProfileResponse } from "@/lib/studentProfile";
import type { User } from "@/lib/types";

const PORTALS = {
  counselor: { nav: "overseas/counselor", roleLabel: "Counselor", back: "/overseas/counselor/students" },
  admin: { nav: "overseas/admin", roleLabel: "Overseas Administrator", back: "/overseas/admin/users" },
} as const;

/** The study destinations a student may prefer (the public catalogue). A failure leaves the picker empty; saved choices still show. */
export async function destinationOptions(): Promise<CountryOption[]> {
  const countries = await publicApi<{ id: string; name: string }[]>("/api/v1/public/countries").catch(() => []);
  return countries.map((c) => ({ id: c.id, name: c.name }));
}

/** ccrm-007 (DEC-SCOPE-249 P1): the overseas student's own Profile section -- every field is theirs to edit. */
export async function MyStudentProfile() {
  let data: StudentProfileResponse;
  try {
    data = await serverApi<StudentProfileResponse>(MY_PROFILE_URL);
  } catch {
    return <div className="card" role="status">Your profile could not be loaded. Refresh the page to try again.</div>;
  }
  return (
    <section className="card" aria-labelledby="my-profile-heading" style={{ marginTop: 16 }}>
      <h3 id="my-profile-heading">My profile</h3>
      <p className="muted">Your academic history, English tests and study preferences. Your counselor sees and can update them too.</p>
      <StudentProfileForm initial={data.profile} url={MY_PROFILE_URL} countries={await destinationOptions()} />
    </section>
  );
}

/** ccrm-007 (DEC-SCOPE-249): /overseas/{counselor|admin}/students/[id]/profile -- ccrm-010's notes page rules: the API is the gate and
 *  the scope (a student outside the caseload is a 404, another role a 403 card), and each reader stays in their own portal. */
export default async function StudentProfilePage({ portal, id }: { portal: keyof typeof PORTALS; id: string }) {
  const { nav, roleLabel, back } = PORTALS[portal];
  let user: User;
  let data: StudentProfileResponse;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<StudentProfileResponse>(studentProfileUrl(id))]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // a malformed id is not found, too
    return accessUnavailable(e, "/overseas/login");
  }
  const own = user.role === "overseas_admin" ? "admin" : "counselor";
  if (own !== portal) redirect(`/overseas/${own}/students/${encodeURIComponent(id)}/profile`);
  return (
    <PortalShell nav={PORTAL_NAV[nav] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={back}>← Back to {portal === "admin" ? "users" : "students"}</Link></p>
        <h1>Profile: {data.student.full_name}</h1>
        <p className="muted">
          {data.student.student_code && <>Student ID {data.student.student_code} · </>}
          <Link href={`/overseas/${portal}/students/${encodeURIComponent(id)}/notes`} style={{ textDecoration: "underline" }}>Notes</Link>
        </p>
        <StudentProfileForm initial={data.profile} url={studentProfileUrl(id)} countries={await destinationOptions()} />
      </div>
    </PortalShell>
  );
}
