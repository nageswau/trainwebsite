import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AgentRegistrationStatus from "@/components/AgentRegistrationStatus";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";

// AGN-024 (DEC-SCOPE-224 K5): reachable while the agency is pending or rejected; no portal navigation, since every other agent page
// is refused until approval.
export default async function Page() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (user.role !== "agent") return accessDenied(user, "Agent role required");
  return (
    <div className="section">
      <div className="container" style={{ maxWidth: 720 }}>
        <AgentRegistrationStatus />
      </div>
    </div>
  );
}
