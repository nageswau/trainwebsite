import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterTemplatesPanel from "@/components/RecruiterTemplatesPanel";
import { serverApi } from "@/lib/api";
import { PARTNERSHIP_HEAD_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { ROLE_LABEL } from "@/lib/partnership";
import { PARTNERSHIP_LIBRARY } from "@/lib/partnershipComms";
import type { User } from "@/lib/types";

// upc-012 (U10, UC4): the partnership head's WhatsApp and email message templates. Partnership managers pick them in the composers on a
// university page; this screen is the head's (and super_admin's). The API enforces who may read and write.
export default async function PartnershipTemplatesPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["partnership_head", "super_admin"].includes(user.role)) return accessDenied(user, "Partnership head role required");
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : PARTNERSHIP_HEAD_NAV} roleLabel={superAdmin ? "Super Administrator" : ROLE_LABEL.head} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">University Partnership CRM</div>
            <h2>Message templates</h2>
            <p className="muted">WhatsApp and email messages partnership managers start from, such as a partnership proposal. They can edit the text before sending. Use placeholders for the contact&apos;s details. Deactivate a template to hide it — it is never deleted.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading templates…</p>}>
          <RecruiterTemplatesPanel library={PARTNERSHIP_LIBRARY} />
        </Suspense>
      </div>
    </PortalShell>
  );
}
