import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, type BdmTeamRow, type BdmType, pageOffset } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import { TEAM_URL } from "@/lib/bdmOrganizations";
import { readPipeline } from "@/lib/bdmPipelineServer";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/pipeline";
const TYPES: BdmType[] = ["agent", "school", "college"];

// bdm-004 (S1, S7, spec §8.3): the team's pipeline per type (super_admin: every BDM), optionally one BDM. Read-only.
export default async function ManagerPipelinePage({ searchParams }: { searchParams: Promise<{ type?: string; bdm?: string; stage?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  let user: User;
  let team: Page<BdmTeamRow>;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    team = await serverApi<Page<BdmTeamRow>>(`${TEAM_URL}?limit=100&offset=0`);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const types = TYPES.filter((t) => team.items.some((b) => b.bdm_type === t));
  const roleLabel = user.role === "super_admin" ? "Super Admin" : "BDM Manager";
  const header = (
    <div className="portal-title">
      <div>
        <div className="eyebrow">Pipeline</div>
        <h2>Team pipeline</h2>
        <p className="muted">Your BDMs&apos; organizations per stage. Lost organizations are counted apart; archived ones are left out.</p>
      </div>
    </div>
  );
  if (types.length === 0) {
    return (
      <PortalShell nav={await nav} roleLabel={roleLabel} userName={user.full_name}>
        <div className="portal-content">
          {header}
          <p className="empty" role="status">No BDMs report to you yet.</p>
        </div>
      </PortalShell>
    );
  }
  const type = types.includes(sp.type as BdmType) ? (sp.type as BdmType) : types[0]; // Review Focus 4
  const ofType = team.items.filter((b) => b.bdm_type === type);
  const picked = ofType.find((b) => b.id === sp.bdm);
  const stage = sp.stage || undefined;
  const offset = pageOffset(sp.offset);
  const href = (change: { stage?: string | null; offset?: number }) => {
    const q = new URLSearchParams({ type });
    if (picked) q.set("bdm", picked.id);
    const s = change.stage === undefined ? stage : change.stage;
    if (s) q.set("stage", s);
    const o = change.offset ?? 0;
    if (o > 0) q.set("offset", String(o));
    return `${PATH}?${q}`;
  };
  let view: Awaited<ReturnType<typeof readPipeline>>;
  try {
    view = await readPipeline({ bdm_type: type, assigned: picked?.id, stage, offset });
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {header}
        <form className="analytics-form" method="get" action={PATH} aria-label="Filter pipeline">
          <div className="field">
            <label htmlFor="pipeline-type">Type</label>
            <select id="pipeline-type" name="type" defaultValue={type}>
              {types.map((t) => <option key={t} value={t}>{BDM_TYPE_LABEL[t]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pipeline-bdm">BDM</label>
            <select id="pipeline-bdm" name="bdm" defaultValue={picked?.id ?? ""}>
              <option value="">Everyone</option>
              {team.items.map((b) => <option key={b.id} value={b.id}>{b.full_name} ({BDM_TYPE_LABEL[b.bdm_type]})</option>)}
            </select>
          </div>
          <button className="btn secondary" type="submit">Show</button>
        </form>
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><Link href={PATH}>Show the team pipeline</Link></p>
          </div>
        ) : (
          <BdmPipelineBoard view={view} href={href} orgBasePath="/bdm/manager/organizations" selected={stage ?? null} emptyText="No organizations at this stage." />
        )}
      </div>
    </PortalShell>
  );
}
