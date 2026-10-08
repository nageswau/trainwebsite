import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import VisitForm from "@/components/VisitForm";
import { serverApi } from "@/lib/api";
import type { PickOption } from "@/lib/lookups";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import { loadUniversity } from "@/lib/universitiesServer";
import { PLANNER_ROLES, VISITS_PATH } from "@/lib/visits";

// upc-010 (VS6): plan a visit. Opened from a university (`?university=<id>`, fixed) or from the visits list (pick one). A partnership
// manager leads their own visits; a head may pick a direct report. The API re-checks the scope on save.
export default async function NewVisitPage({ searchParams }: { searchParams: Promise<{ university?: string }> }) {
  const { university: universityId } = await searchParams;
  let user: User, university: PickOption | null = null, refusal: string | null = null;
  try {
    const [me, uni] = await Promise.all([serverApi<User>("/api/v1/auth/me"), universityId ? loadUniversity(universityId) : Promise.resolve(null)]);
    user = me;
    if (uni) {
      university = { id: uni.id, label: uni.name, detail: `${uni.university_code} · ${[uni.city, uni.country.name].filter(Boolean).join(", ")}` };
      if (!uni.active) refusal = "Reactivate this university before planning a visit to it.";
      else if (!uni.permissions.can_edit_contacts) refusal = "Only the university's partnership managers can plan a visit to it.";
    }
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const back = universityId ? universityPath(universityId) : VISITS_PATH;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={back}>{universityId ? "University" : "University Visits"}</Link></div>
            <h2>Plan a university visit</h2>
            <p className="muted">The visit starts as a draft. Submit it for approval when the plan is ready.</p>
          </div>
        </div>
        {PLANNER_ROLES.has(user.role) && !refusal ? (
          <VisitForm university={university} canPickLead={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">
            {PLANNER_ROLES.has(user.role) ? refusal : "Only partnership managers and heads plan visits."}{" "}
            <Link href={back}>Go back</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
