import { ApiError, serverApi } from "@/lib/api";
import { dashboardPathFor } from "@/lib/navigation";
import type { User } from "@/lib/types";

import ReturnToLoginLink from "./ReturnToLoginLink";
import SignOutButton from "./SignOutButton";

// The card a portal page shows when its data cannot be read. It used to offer "Return to login" to everyone, including a signed-in
// user who simply lacks the role (browser QA-14, found in ENH-011's QA). Signed out (401) still gets the login link; anyone else is
// sent to their own dashboard, looked up from the session -- and if even that cannot be read, back to login.

// AGN-001 (browser QA-02): an agent refused for its agency's or its own account state is already ON its dashboard, so "Go to
// your dashboard" only reloaded the same page. These reasons get guidance instead (texts are core/rbac.py's gate messages).
const AGENT_ACCOUNT_STATE_REASONS = new Set(["Agent registration is pending approval", "Your agency's account is suspended", "Your Master account is deactivated"]);
// bdm-001 (review deferred minor): a BDM whose profile is missing is likewise ON its dashboard (/bdm/my-day); the message itself
// already says whom to contact (text is services/bdm.py bdm_context's).
const BDM_ACCOUNT_STATE_REASONS = new Set(["BDM profile not set up — contact your administrator"]);

function AccessUnavailableCard({ message, home, loginHref }: { message: string; home: string | null; loginHref: string }) {
  const agentAccountState = AGENT_ACCOUNT_STATE_REASONS.has(message);
  const accountState = agentAccountState || BDM_ACCOUNT_STATE_REASONS.has(message);
  return (
    <div className="section">
      <div className="container card">
        <h1>Access unavailable</h1>
        <p>{message}</p>
        {agentAccountState && <p className="muted">Contact EduSphere Overseas Admin if you think this is a mistake.</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {home ? !accountState && <a className="btn" href={home}>Go to your dashboard</a> : <ReturnToLoginLink loginHref={loginHref} />}
          {home && <SignOutButton redirectTo={loginHref} />}
        </div>
      </div>
    </div>
  );
}

/** For a page that has already read the session and is refusing the user itself: no lookup, the dashboard comes from the user in
 * hand. `accessUnavailable` is for the catch path, where there may be no session at all. */
export function accessDenied(user: User, message: string) {
  return <AccessUnavailableCard message={message} home={dashboardPathFor(user)} loginHref="/overseas/login" />;
}

/** Pages `return accessUnavailable(e)` from their own async body, so the lookup happens there and the page still resolves to plain
 * JSX (an async component inside JSX would not render in the page tests). */
export async function accessUnavailable(error: unknown, loginHref = "/overseas/login") {
  const message = error instanceof Error ? error.message : "Unable to load this workspace";
  let home: string | null = null;
  if (!(error instanceof ApiError && error.status === 401)) {
    try {
      const user = await serverApi<User>("/api/v1/auth/me");
      home = dashboardPathFor(user);
    } catch {
      home = null;
    }
  }
  return <AccessUnavailableCard message={message} home={home} loginHref={loginHref} />;
}
