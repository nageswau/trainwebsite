import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterPipelineBoard from "@/components/RecruiterPipelineBoard";
import { ApiError, serverApi } from "@/lib/api";
import { pageOffset } from "@/lib/bdm";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { BOARD_URL, type BoardView, PIPELINE_PATH } from "@/lib/recruiterPipeline";
import type { User } from "@/lib/types";

// rec-005 (P7): companies per stage in the caller's scope -- a recruiter's own, a manager's team and the unassigned queue, everything for
// super admin. Lost companies are counted apart; archived ones are left out. Filters live in the address.
export default async function RecruiterPipelinePage({ searchParams }: { searchParams: Promise<{ stage?: string; offset?: string }> }) {
  const sp = await searchParams;
  const stage = sp.stage || undefined;
  const offset = pageOffset(sp.offset);
  const href = (change: { stage?: string | null; offset?: number }) => {
    const q = new URLSearchParams();
    const s = change.stage === undefined ? stage : change.stage;
    if (s) q.set("stage", s);
    const o = change.offset ?? 0;
    if (o > 0) q.set("offset", String(o));
    const query = q.toString();
    return query ? `${PIPELINE_PATH}?${query}` : PIPELINE_PATH;
  };
  let user: User;
  let view: BoardView | "invalid";
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    const q = new URLSearchParams({ limit: "50", offset: String(offset) });
    if (stage) q.set("stage", stage);
    view = await serverApi<BoardView>(`${BOARD_URL}?${q}`).catch((e) => {
      if (e instanceof ApiError && e.status === 422) return "invalid" as const;
      throw e;
    });
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Pipeline</div>
            <h2>Company pipeline</h2>
            <p className="muted">Companies per stage. Lost companies are counted apart; archived ones are left out.</p>
          </div>
        </div>
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><a href={PIPELINE_PATH}>Show the whole pipeline</a></p>
          </div>
        ) : (
          <RecruiterPipelineBoard view={view} href={href} selected={stage ?? null} />
        )}
      </div>
    </PortalShell>
  );
}
