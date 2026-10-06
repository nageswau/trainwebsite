import Link from "next/link";
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import LeadDetailPanel from "@/components/LeadDetailPanel";
import NewLeadForm from "@/components/NewLeadForm";
import PortalShell from "@/components/PortalShell";
import TelecallerLeadTable from "@/components/TelecallerLeadTable";
import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { TELECALLER_MANAGER_NAV, TELECALLER_NAV, TELECALLER_SIGN_IN, type NavItem } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";
import { TIMELINE_LIMIT, leadUrl, type TelecallerLeadDetail, type TimelineRow } from "@/lib/telecallerLeads";
import type { User } from "@/lib/types";

// tel-008 (spec §3, D5): My Leads and the lead detail, for a telecaller (/telecaller/leads) and a manager (/telecaller/manager/leads).
// The API is the gate and the scope; the role check here only spares other roles a screen that can only fail.
type Shell = { nav: NavItem[]; roleLabel: string; userName: string };

async function shellFor(manager: boolean): Promise<Shell | React.ReactElement> {
  if (!manager) {
    try {
      const me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
      return { nav: TELECALLER_NAV, roleLabel: teamRoleLabel(me.telecaller_profile.team), userName: me.full_name };
    } catch (e) {
      return accessUnavailable(e, TELECALLER_SIGN_IN);
    }
  }
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["telecaller_manager", "super_admin"].includes(user.role)) return accessDenied(user, "Telecaller manager role required");
  return { nav: TELECALLER_MANAGER_NAV, roleLabel: user.role === "super_admin" ? "Super Administrator" : "Telecaller Manager", userName: user.full_name };
}

const basePath = (manager: boolean) => (manager ? "/telecaller/manager/leads" : "/telecaller/leads");

export async function TelecallerLeadsPage({ manager }: { manager: boolean }) {
  const shell = await shellFor(manager);
  if (!("nav" in shell)) return shell;
  return (
    <PortalShell nav={shell.nav} roleLabel={shell.roleLabel} userName={shell.userName}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Leads</div>
            <h2>{manager ? "Team leads" : "My leads"}</h2>
            <p className="muted">
              {manager ? "Leads of the telecallers who report to you, and your teams' unassigned leads." : "The leads assigned to you. Open a lead to call, update it or set its priority."}
            </p>
          </div>
          <Link className="btn" href={`${basePath(manager)}/new`}>New lead</Link>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading leads…</p>}>
          <TelecallerLeadTable basePath={basePath(manager)} showTelecaller={manager} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

/** tel-005 (spec §4): the New Lead form. A telecaller's lead is theirs; a manager's waits in the team's unassigned queue (I2). */
export async function TelecallerNewLeadPage({ manager }: { manager: boolean }) {
  const shell = await shellFor(manager);
  if (!("nav" in shell)) return shell;
  return (
    <PortalShell nav={shell.nav} roleLabel={shell.roleLabel} userName={shell.userName}>
      <div className="portal-content">
        <p style={{ margin: "0 0 12px" }}><Link href={basePath(manager)}>← Back to leads</Link></p>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Leads</div>
            <h2>New lead</h2>
            <p className="muted">
              {manager ? "The lead goes to your team's telecallers by your distribution rules, or waits in the unassigned queue." : "The lead is assigned to you."} We check the mobile number and email
              against every lead first, so a person is never entered twice.
            </p>
          </div>
        </div>
        <NewLeadForm basePath={basePath(manager)} />
      </div>
    </PortalShell>
  );
}

/** One lead. A 404 (unknown or outside the caller's scope) or a malformed id (422) is a plain "not found" -- it never says which. */
export async function TelecallerLeadPage({ id, manager }: { id: string; manager: boolean }) {
  const shell = await shellFor(manager);
  if (!("nav" in shell)) return shell;
  const timeline = serverApi<Page<TimelineRow>>(leadUrl(id, `/timeline?limit=${TIMELINE_LIMIT}`)).catch(() => null);
  let lead: TelecallerLeadDetail | null = null;
  try {
    lead = await serverApi<TelecallerLeadDetail>(leadUrl(id));
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, manager ? "/admin/login" : TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={shell.nav} roleLabel={shell.roleLabel} userName={shell.userName}>
      <div className="portal-content">
        <p style={{ margin: "0 0 12px" }}><Link href={basePath(manager)}>← Back to leads</Link></p>
        {lead ? (
          <LeadDetailPanel initial={lead} timeline={await timeline} canReopen={manager} />
        ) : (
          <div className="action-card">
            <h2>Lead not found</h2>
            <p>This lead does not exist, or it is not in your leads.</p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
