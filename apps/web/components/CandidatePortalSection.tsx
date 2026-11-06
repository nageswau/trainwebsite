import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalSection from "@/components/PortalSection";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { CANDIDATE_NAV } from "@/lib/candidatePortal";
import type { PortalPayload, User } from "@/lib/types";

type Header = Pick<PortalPayload, "title" | "subtitle"> & Partial<Pick<PortalPayload, "actions">>;

// hrc-031 (DEC-SCOPE-412 P1): one section of the candidate portal -- the candidate's own shell around the student portal's section layout.
// `url` reads a section payload (a table); otherwise `header` titles a page whose `lead` brings its own card. Any other role gets the 403 card.
export default async function CandidatePortalSection({ url, header, lead, emptyText }: { url?: string; header?: Header; lead?: React.ReactNode; emptyText?: string }) {
  let user: User;
  let data: PortalPayload;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "candidate") throw new ApiError("Only candidates can use the candidate portal", 403);
    data = url ? await serverApi<PortalPayload>(url) : { title: "", subtitle: "", columns: [], rows: [], metrics: [], actions: [], panels: [], ...header };
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={CANDIDATE_NAV} roleLabel="Candidate" userName={user.full_name}>
      <PortalSection data={data} eyebrow="Candidate portal" countBadge={false} table={Boolean(url)} lead={lead && <div style={{ marginBottom: 16 }}>{lead}</div>} emptyText={emptyText} />
    </PortalShell>
  );
}
