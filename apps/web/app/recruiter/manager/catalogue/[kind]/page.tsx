import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCampaignsPanel from "@/components/RecruiterCampaignsPanel";
import RecruiterCatalogueValuesPanel from "@/components/RecruiterCatalogueValuesPanel";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";
import { CATALOGUE_PATH, TABS, isTab } from "@/lib/recruiterCatalogue";
import type { User } from "@/lib/types";

// rec-002: the placement manager's managed lists, one tab each (the tel-002 catalogue screens, as tabs). Managers and super_admin
// edit; the role check only spares other roles a screen that can only fail -- the API enforces who may read and write.
export default async function RecruiterCataloguePage({ params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  if (!isTab(kind)) notFound();
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["placement_manager", "super_admin"].includes(user.role)) return accessDenied(user, "Placement manager role required");
  const superAdmin = user.role === "super_admin";
  const tab = TABS[kind];
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : RECRUITER_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : PLACEMENT_MANAGER_LABEL} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Catalogues</div>
            <h2>{tab.label}</h2>
            <p className="muted">{tab.intro} Deactivate a value to hide it from pickers — records that already use it keep it.</p>
          </div>
        </div>
        <nav aria-label="Catalogues" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {Object.entries(TABS).map(([slug, t]) => (
            <Link key={slug} href={`${CATALOGUE_PATH}/${slug}`} aria-current={slug === kind ? "page" : undefined} className={`btn small${slug === kind ? "" : " secondary"}`}>
              {t.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <Suspense fallback={<p className="muted" role="status">Loading…</p>}>
            {kind === "campaigns" ? <RecruiterCampaignsPanel /> : <RecruiterCatalogueValuesPanel key={kind} kind={kind} />}
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
