import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmMousPanel from "@/components/BdmMousPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { pageOffset } from "@/lib/bdm";
import type { MouStatus } from "@/lib/bdmMous";
import { readMous } from "@/lib/bdmMousServer";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/mous";

// bdm-005 (spec §8, M3): the team's MoUs (super_admin: every BDM's), filtered by derived status in the address. Read-only.
export default async function ManagerMousPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const status = (sp.status || undefined) as MouStatus | undefined;
  let user: User;
  let page: Awaited<ReturnType<typeof readMous>>;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    page = await readMous({ status, offset: pageOffset(sp.offset) });
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">MoUs</div>
            <h2>Team MoUs</h2>
            <p className="muted">Your BDMs&apos; current MoUs. A Signed or Active MoU past its valid-until date reads Expired.</p>
          </div>
        </div>
        {page === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><a href={PATH}>Show all MoUs</a></p>
          </div>
        ) : (
          <BdmMousPanel page={page} status={status ?? null} path={PATH} orgBasePath="/bdm/manager/organizations" />
        )}
      </div>
    </PortalShell>
  );
}
