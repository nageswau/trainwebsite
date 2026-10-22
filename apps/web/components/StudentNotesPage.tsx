import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import StudentNotesPanel from "@/components/StudentNotesPanel";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { studentNotesUrl, type StudentNotes } from "@/lib/studentNotes";
import type { User } from "@/lib/types";

const PORTALS = {
  counselor: { nav: "overseas/counselor", roleLabel: "Counselor", back: "/overseas/counselor/students" },
  admin: { nav: "overseas/admin", roleLabel: "Overseas Administrator", back: "/overseas/admin/users" },
} as const;

/** ccrm-010 (DEC-SCOPE-241): /overseas/{counselor|admin}/students/[id]/notes. The API is the gate and the scope -- a student outside the
 *  counselor's caseload is a 404, another role a 403 card. ccrm-009's student 360 will host the same panel in its Activities tab. */
export default async function StudentNotesPage({ portal, id }: { portal: keyof typeof PORTALS; id: string }) {
  const { nav, roleLabel, back } = PORTALS[portal];
  let user: User;
  let notes: StudentNotes;
  try {
    [user, notes] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<StudentNotes>(`${studentNotesUrl(id)}?limit=20&offset=0`)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // QA-01: a malformed id is not found, too
    return accessUnavailable(e, "/overseas/login");
  }
  // QA-02: each reader sees the notes inside their own portal (nav and role label), whichever address they opened.
  const own = user.role === "overseas_admin" ? "admin" : "counselor";
  if (own !== portal) redirect(`/overseas/${own}/students/${encodeURIComponent(id)}/notes`);
  return (
    <PortalShell nav={PORTAL_NAV[nav] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={back}>← Back to {portal === "admin" ? "users" : "students"}</Link></p>
        <h1>Notes: {notes.student.full_name}</h1>
        <p className="muted">
          {notes.student.student_code && <>Student ID {notes.student.student_code} · </>}Internal notes — the student and the agent never see them.
        </p>
        <StudentNotesPanel initial={notes} />
      </div>
    </PortalShell>
  );
}
