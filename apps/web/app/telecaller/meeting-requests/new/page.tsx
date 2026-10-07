import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingRequestForm from "@/components/MeetingRequestForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { telecallerNav } from "@/lib/telecallerNav";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-019 (EVID-019 §9): file a BDM meeting request.
export default async function NewMeetingRequestPage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={await telecallerNav()} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">BDM requests</div>
            <h2>Request a BDM meeting</h2>
            <p className="muted">
              Pick a BDM, or leave it for any BDM of the meeting&apos;s module. Corporate meetings go to college BDMs.{" "}
              <Link href="/telecaller/meeting-requests" style={LINK_STYLE}>Back to requests</Link>
            </p>
          </div>
        </div>
        <div className="action-card wide">
          <MeetingRequestForm />
        </div>
      </div>
    </PortalShell>
  );
}
