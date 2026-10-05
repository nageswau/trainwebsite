import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import Student360View from "@/components/Student360View";
import { serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";
import { loadStudent360, type Student360 } from "@/lib/student360";
import type { User } from "@/lib/types";

// ENH-013 -- what the seven per-role `/360` routes share (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §8).
// Each route stays its own thin file (the app's per-role-route convention) and only says which portal it is in and where "back"
// goes; loading, the refusal card and the page body live here once. The API enforces each role's scope (spec §6.1/§6.3).

export type Student360Portal = { nav: NavItem[]; roleLabel: string; backHref: (studentId: string) => string; backLabel: string };
export type Student360RouteProps = { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> };

// A plain async function, not an async component: pages `return` it, so the page resolves to plain JSX (as `accessUnavailable`
// does), which the page tests can render.
export async function renderStudent360Route(portal: Student360Portal, { params, searchParams }: Student360RouteProps) {
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  let user: User;
  let data: Student360;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadStudent360(id)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={portal.nav} roleLabel={portal.roleLabel} userName={user.full_name}>
      <Student360View data={data} initialTab={tab} backHref={portal.backHref(id)} backLabel={portal.backLabel} />
    </PortalShell>
  );
}

// The routes' loading.tsx: shaped like the header card, the tab list and one panel, so the page does not jump when it loads.
export function Student360Loading({ nav, roleLabel }: Pick<Student360Portal, "nav" | "roleLabel">) {
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading the student 360° view">
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "40%" }} /></div>
        <div className="s360-layout">
          <div className="card">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton-line" style={{ marginBottom: 8 }} />)}</div>
          <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" /></div>
        </div>
      </div>
    </PortalShell>
  );
}
