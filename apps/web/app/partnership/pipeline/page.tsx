import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipPipelineBoard from "@/components/PartnershipPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { type Board, type BoardChange, boardHref, boardQuery, PIPELINE_PATH, PIPELINE_URL } from "@/lib/partnershipPipeline";
import { pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

const TOGGLE = { display: "flex", gap: 8, flexWrap: "wrap", margin: "0 0 16px" } as const;

// upc-007 (PS11, PS12): the §4 Kanban pipeline for every role that reads the University Master. A manager starts on their own universities
// (primary or backup) with an "All universities" toggle; heads, overseas_admin and super_admin see every one. Filters live in the address.
export default async function PartnershipPipelinePage({ searchParams }: { searchParams: Promise<{ scope?: string; column?: string; offset?: string }> }) {
  const sp = await searchParams;
  const column = sp.column || undefined;
  const offset = pageOffset(sp.offset);
  let user: User;
  let view: Board | "invalid";
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    const mine = user.role === "partnership_manager" && sp.scope !== "all";
    view = await serverApi<Board>(`${PIPELINE_URL}?${boardQuery({ mine, column, offset })}`).catch((e) => {
      if (e instanceof ApiError && e.status === 422) return "invalid" as const; // a hand-edited column or offset
      throw e;
    });
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const isManager = user.role === "partnership_manager";
  const all = !isManager || sp.scope === "all";
  const href = (change: BoardChange, scopeAll = all) =>
    boardHref({ all: isManager && scopeAll, column: change.column === undefined ? column : change.column, offset: change.offset ?? 0 });
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Partnership Pipeline</div>
            <h2>Partnership pipeline</h2>
            <p className="muted">Universities per Kanban column. Lost universities are counted apart; inactive ones are left out.</p>
          </div>
        </div>
        {isManager && (
          <nav aria-label="Whose universities" style={TOGGLE}>
            {/* plain links (a full page load), as the board's filters; the chosen column is kept, the page is not */}
            <a className={all ? "btn secondary small" : "btn small"} href={href({}, false)} aria-current={all ? undefined : "true"}>My universities</a>
            <a className={all ? "btn small" : "btn secondary small"} href={href({}, true)} aria-current={all ? "true" : undefined}>All universities</a>
          </nav>
        )}
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><a href={PIPELINE_PATH}>Show the whole pipeline</a></p>
          </div>
        ) : (
          <PartnershipPipelineBoard view={view} href={href} selected={column ?? null} />
        )}
      </div>
    </PortalShell>
  );
}
