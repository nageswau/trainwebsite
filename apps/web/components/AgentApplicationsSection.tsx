"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import AgentApplicationCreatePanel from "./AgentApplicationCreatePanel";
import AgentApplicationsPanel from "./AgentApplicationsPanel";
import { parseGroup } from "@/lib/agentApplications";
import type { User } from "@/lib/types";

// AGN-008: the agency Applications page -- create, then the list for the sidebar filter in the URL (?status=). Staff see only
// their assigned students' applications (G4); a non-agency viewer (Super Admin) gets a note, as on the Students page.
function Filtered({ reloadKey, isMaster }: { reloadKey: number; isMaster: boolean }) {
  const group = parseGroup(useSearchParams().get("status"));
  return <AgentApplicationsPanel key={group} group={group} reloadKey={reloadKey} isMaster={isMaster} />;
}

export default function AgentApplicationsSection({ user }: { user: User }) {
  const [reloadKey, setReloadKey] = useState(0);
  const member = user.role === "agent";
  const intro = !member
    ? "Agency applications are managed by the agency's own Masters and Staff."
    : user.agent_member_role === "staff"
      ? "Applications of students assigned to you, with or without a login."
      : "Every application of your agency, for students with or without a login.";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Applications</h2>
          <p className="muted">{intro}</p>
        </div>
      </div>
      {member && (
        <div className="action-grid">
          <AgentApplicationCreatePanel onCreated={() => setReloadKey((k) => k + 1)} />
          <Suspense fallback={<p className="muted">Loading applications…</p>}>
            <Filtered reloadKey={reloadKey} isMaster={user.agent_member_role !== "staff"} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
