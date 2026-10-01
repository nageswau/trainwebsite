import AgentStudentsPanel from "./AgentStudentsPanel";
import type { User } from "@/lib/types";

// The agency Students page intro and panel (moved out of PortalPage for AGN-005 browser QA, owner 2026-10-01).
// QA5-03: staff see only their assigned students (DEC-SCOPE-042 G4), so their intro says so.
// QA5-05: the panel's API admits agency members only (API_CONTRACT AGN-004 table); anyone else who can open the portal page (a
// Super Admin) gets a note instead of a panel whose every action is refused.
export default function AgentStudentsSection({ user }: { user: User }) {
  const member = user.role === "agent";
  const intro = !member
    ? "Agency student records are managed by the agency's own Masters and Staff."
    : user.agent_member_role === "staff"
      ? "Students assigned to you, with or without a login. Those who have a login also appear under Application status below."
      : "Every student of your agency, with or without a login. Students who have a login also appear under Application status below.";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Students</h2>
          <p className="muted">{intro}</p>
        </div>
      </div>
      {member && (
        <div className="action-grid">
          <AgentStudentsPanel memberRole={user.agent_member_role} />
        </div>
      )}
    </div>
  );
}
