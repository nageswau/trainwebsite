import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ItStudent360View from "@/components/ItStudent360View";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PORTALS, student360Path, student360Url, type Portal360, type Student360 } from "@/lib/itStudent360";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

function ownPortal(user: User): Portal360 | null {
  if (user.role === "it_admin") return "admin";
  if (user.role === "counselor" && user.division === "it") return "counselor";
  if (user.role === "hr_team") return "hr";
  return null;
}

/** itc-029 (DEC-SCOPE-359): /it/counselor/students/[id], /it/admin/students/[id] and /it/hr/students/[id]/360. The API is the gate, the
 *  scope and the section allow-list -- a student outside the reader's scope is a 404, another role a 403 card -- and each reader stays in
 *  their own portal (itc-028's pattern). Rendered on the server per request, so every section is the source record as it is now (AC1). */
export default async function ItStudent360Page({ portal, id }: { portal: Portal360; id: string }) {
  let user: User;
  let data: Student360;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  const own = ownPortal(user);
  if (own && own !== portal) redirect(student360Path(own, id));
  try {
    data = await serverApi<Student360>(student360Url(id));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound(); // a malformed id is not found, too
    return accessUnavailable(e, "/it/login");
  }
  const { roleLabel, back, backLabel } = PORTALS[portal];
  const sid = encodeURIComponent(data.student.id);
  return (
    <PortalShell nav={PORTAL_NAV[`it/${portal}`] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={back}>← Back to {backLabel}</Link></p>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Student 360{data.student.student_code ? ` · ${data.student.student_code}` : ""}{data.student.active ? "" : " · deactivated"}</div>
            <h2>{data.student.full_name}</h2>
            <p className="muted">Read only. Each section is the live record; edit it on its own page.</p>
          </div>
          <div className="actions">
            {portal === "hr" ? (
              <Link className="btn small secondary" href={`/it/hr/students/${sid}`}>Training detail</Link>
            ) : (
              <Link className="btn small secondary" href={`/it/${portal}/students/${sid}/profile`}>Profile</Link>
            )}{" "}
            <Link className="btn small secondary" href={`/it/${portal}/students/${sid}/notes`}>Notes</Link>
          </div>
        </div>
        <ItStudent360View portal={portal} data={data} />
      </div>
    </PortalShell>
  );
}
