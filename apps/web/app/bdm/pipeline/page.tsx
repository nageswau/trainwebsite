import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe, pageOffset } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { readPipeline } from "@/lib/bdmPipelineServer";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/pipeline";
const TOGGLE = { display: "flex", gap: 8, flexWrap: "wrap", margin: "0 0 16px" } as const;

// bdm-004 (S7, spec §8.3): my pipeline by default; "All in module" is the D11 read scope. Filters live in the address.
export default async function BdmPipelinePage({ searchParams }: { searchParams: Promise<{ scope?: string; stage?: string; offset?: string }> }) {
  const nav = bdmNav();
  const sp = await searchParams;
  const all = sp.scope === "all";
  const stage = sp.stage || undefined;
  const offset = pageOffset(sp.offset);
  const href = (change: { stage?: string | null; offset?: number }, scopeAll = all) => {
    const q = new URLSearchParams();
    if (scopeAll) q.set("scope", "all");
    const s = change.stage === undefined ? stage : change.stage;
    if (s) q.set("stage", s);
    const o = change.offset ?? 0;
    if (o > 0) q.set("offset", String(o));
    const query = q.toString();
    return query ? `${PATH}?${query}` : PATH;
  };
  let me: BdmMe;
  let view: Awaited<ReturnType<typeof readPipeline>>;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
    view = await readPipeline({ assigned: all ? undefined : "me", stage, offset });
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = BDM_TYPE_LABEL[me.bdm_profile.bdm_type];
  return (
    <PortalShell nav={await nav} roleLabel={`${type} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Pipeline</div>
            <h2>{type} pipeline</h2>
            <p className="muted">Organizations per stage. Lost organizations are counted apart; archived ones are left out.</p>
          </div>
        </div>
        <nav aria-label="Whose organizations" style={TOGGLE}>
          {/* QA4-01: plain links (a full page load), as the board's filters; QA4-10: the chosen stage is kept, the page is not */}
          <a className={all ? "btn secondary small" : "btn small"} href={href({}, false)} aria-current={all ? undefined : "true"}>Mine</a>
          <a className={all ? "btn small" : "btn secondary small"} href={href({}, true)} aria-current={all ? "true" : undefined}>All in module</a>
        </nav>
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><a href={PATH}>Show my pipeline</a></p>
          </div>
        ) : (
          <BdmPipelineBoard
            view={view}
            href={href}
            orgBasePath="/bdm/organizations"
            selected={stage ?? null}
            emptyText="No organizations at this stage."
            emptyAction={<Link className="btn small" href="/bdm/organizations/new">Add organization</Link>}
          />
        )}
      </div>
    </PortalShell>
  );
}
