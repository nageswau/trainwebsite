import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ItStudentNotesPanel from "@/components/ItStudentNotesPanel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { itStudentNotesUrl, PAGE_SIZE, type ItStudentNotes } from "@/lib/itStudentNotes";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const PORTALS = {
  counselor: { roleLabel: "Counselor", back: "/it/counselor/students", backLabel: "my students" },
  admin: { roleLabel: "IT Administrator", back: "/it/admin/students", backLabel: "students" },
  hr: { roleLabel: "HR Team", back: "/it/hr/students", backLabel: "students" },
  trainer: { roleLabel: "Trainer", back: "/it/trainer/student-progress", backLabel: "student progress" },
} as const;
type Portal = keyof typeof PORTALS;

function ownPortal(user: User): Portal | null {
  if (user.role === "it_admin") return "admin";
  if (user.role === "counselor" && user.division === "it") return "counselor";
  if (user.role === "hr_team") return "hr";
  if (user.role === "trainer") return "trainer";
  return null;
}

/** itc-028 (DEC-SCOPE-351): /it/{counselor|admin|hr|trainer}/students/[id]/notes. The API is the gate and the scope -- a student outside
 *  the reader's scope is a 404, another role a 403 card -- and each reader stays in their own portal (QA-01 pattern). */
export default async function ItStudentNotesPage({ portal, id }: { portal: Portal; id: string }) {
  let user: User;
  let notes: ItStudentNotes;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  const own = ownPortal(user);
  if (own && own !== portal) redirect(`/it/${own}/students/${encodeURIComponent(id)}/notes`);
  try {
    notes = await serverApi<ItStudentNotes>(`${itStudentNotesUrl(id)}?limit=${PAGE_SIZE}&offset=0`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // a malformed id is not found, too
    return accessUnavailable(e, "/it/login");
  }
  const { roleLabel, back, backLabel } = PORTALS[portal];
  return (
    <PortalShell nav={PORTAL_NAV[`it/${portal}`] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={back}>← Back to {backLabel}</Link></p>
        <h1>Notes: {notes.student.full_name}</h1>
        <p className="muted">
          {notes.student.student_code && <>Student ID {notes.student.student_code} · </>}Notes are internal. The student sees only a note its author shares with them.
        </p>
        <ItStudentNotesPanel initial={notes} />
      </div>
    </PortalShell>
  );
}
