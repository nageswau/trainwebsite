import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import VisitForm from "@/components/VisitForm";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";
import { type Visit, visitPath } from "@/lib/visits";
import { loadVisit } from "@/lib/visitsServer";

// upc-010 (VS8, VS9): edit a visit. Only its lead or planner sees the form, with the fields its status still allows; the API re-checks.
export default async function EditVisitPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, v: Visit;
  try {
    [user, v] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadVisit(id)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={visitPath(v.id)}>{v.code}</Link></div>
            <h2>Edit the visit to {v.university.name}</h2>
            {v.status !== "planned" && <p className="muted">The approved plan is locked. Dates, notes, contacts and the agenda can still change.</p>}
          </div>
        </div>
        {v.permissions.can_edit ? (
          <VisitForm visit={v} canPickLead={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">
            {v.approval_state === "waiting" ? "This visit is waiting for approval and can't be edited." : v.status === "closed" ? "This visit is closed." : "Only the visit's lead or the person who planned it can edit it."}{" "}
            <Link href={visitPath(v.id)}>Back to the visit</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
