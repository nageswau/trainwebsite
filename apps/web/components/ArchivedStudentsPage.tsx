import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import StudentArchiveControls from "@/components/StudentArchiveControls";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { ARCHIVED_STUDENTS_URL, type ArchivedStudent } from "@/lib/overseasStudent360";
import type { User } from "@/lib/types";

const PAGE_SIZE = 20;
const PORTALS = {
  counselor: { nav: "overseas/counselor", role: "counselor", roleLabel: "Counselor", intro: "Your archived students. The Overseas Admin can restore them." },
  admin: {
    nav: "overseas/admin", role: "overseas_admin", roleLabel: "Overseas Administrator",
    intro: "Every archived overseas student. Restore one to put them and their applications back in the working lists.",
  },
} as const;

/** ccrm-040 (DEC-SCOPE-276 AR7): /overseas/{counselor|admin}/archived-students -- archived students, newest first, each opening the
 *  read-only 360; the Overseas Admin restores from here. */
export default async function ArchivedStudentsPage({ portal, offset }: { portal: keyof typeof PORTALS; offset: number }) {
  const { nav, role, roleLabel, intro } = PORTALS[portal];
  let user: User, data: { items: ArchivedStudent[]; total: number };
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== role || user.division !== "overseas") return accessDenied(user, `${roleLabel} role required`);
    data = await serverApi(`${ARCHIVED_STUDENTS_URL}?limit=${PAGE_SIZE}&offset=${offset}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const base = `/overseas/${portal}`;
  return (
    <PortalShell nav={PORTAL_NAV[nav] ?? []} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Archived students</h2>
            <p className="muted">{intro}</p>
          </div>
        </div>
        {data.items.length === 0 ? (
          <div className="card"><p className="muted" style={{ margin: 0 }}>No archived students.</p></div>
        ) : (
          <ul className="s360-list">
            {data.items.map((s) => (
              <li key={s.id}>
                <p style={{ margin: "0 0 6px" }}>
                  <Link href={`${base}/students/${encodeURIComponent(s.id)}`}><strong>{s.full_name}</strong></Link>
                  <span className="muted"> · {[s.student_code && `Student ID ${s.student_code}`, s.email].filter(Boolean).join(" · ")}</span>
                </p>
                <StudentArchiveControls studentId={s.id} archive={s} permissions={{ archive: false, restore: portal === "admin" }} />
              </li>
            ))}
          </ul>
        )}
        {data.total > PAGE_SIZE && (
          <nav aria-label="Pages" style={{ display: "flex", gap: 12, marginTop: 12 }}>
            {offset > 0 && <Link href={`${base}/archived-students?offset=${Math.max(0, offset - PAGE_SIZE)}`}>← Newer</Link>}
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}</span>
            {offset + PAGE_SIZE < data.total && <Link href={`${base}/archived-students?offset=${offset + PAGE_SIZE}`}>Older →</Link>}
          </nav>
        )}
      </div>
    </PortalShell>
  );
}

export function pageOffset(value: string | string[] | undefined): number {
  const n = Number(Array.isArray(value) ? value[0] : value);
  return Number.isInteger(n) && n > 0 ? n : 0;
}
