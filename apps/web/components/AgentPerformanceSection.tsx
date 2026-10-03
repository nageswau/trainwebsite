import AgentPerformancePanel from "./AgentPerformancePanel";
import type { User } from "@/lib/types";

// AGN-019 (DEC-SCOPE-063 P7; spec §6.2a): the Staff Performance page frame (the AgentTasksSection pattern). Only an agency Master
// gets the panel; anyone else who opens the address is told so without a request -- the server refuses them (403) regardless.
export default function AgentPerformanceSection({ user }: { user: User }) {
  const master = user.role === "agent" && user.agent_member_role !== "staff";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Staff performance</h2>
          <p className="muted">Students added in a period, and how far they got.</p>
        </div>
      </div>
      {master ? <AgentPerformancePanel /> : <p className="muted">Staff performance is available to agency Masters.</p>}
    </div>
  );
}
