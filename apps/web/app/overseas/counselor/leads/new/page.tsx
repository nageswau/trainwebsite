import Link from "next/link";
import { notFound } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import NewLeadForm from "@/components/NewLeadForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { WALK_IN_LEAD_API } from "@/lib/leadHandover";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const LEADS = "/overseas/counselor/leads";

// csc-004 (DEC-SCOPE-229; W1, W4, W5): an overseas counselor records a walk-in as a lead. It is theirs, a telecaller is assigned by the
// team's distribution rules (read-only for them), and it opens in My leads. The API is the gate; another role never sees this page.
export default async function NewWalkInLeadPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (user.role !== "counselor" || user.division !== "overseas") notFound();
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"] ?? []} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <p style={{ margin: "0 0 12px" }}><Link href={LEADS}>← Back to my leads</Link></p>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Leads</div>
            <h2>New walk-in lead</h2>
            <p className="muted">
              For a student who came to the office. The lead is yours; a telecaller from the Overseas team is also assigned and can see it.
              We check the mobile number and email against every lead first, so a person is never entered twice.
            </p>
          </div>
        </div>
        <NewLeadForm basePath={LEADS} api={WALK_IN_LEAD_API} initial={{ source: "walk_in" }} team="overseas" />
      </div>
    </PortalShell>
  );
}
