import { ApiError, serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import type { User } from "@/lib/types";

// The card a portal page shows when its data cannot be read. It used to offer "Return to login" to everyone, including a signed-in
// user who simply lacks the role (browser QA-14, found in ENH-011's QA). Signed out (401) still gets the login link; anyone else is
// sent to their own dashboard, looked up from the session -- and if even that cannot be read, back to login.

function AccessUnavailableCard({ message, home, loginHref }: { message: string; home: string | null; loginHref: string }) {
  return (
    <div className="section">
      <div className="container card">
        <h1>Access unavailable</h1>
        <p>{message}</p>
        {home ? <a className="btn" href={home}>Go to your dashboard</a> : <a className="btn" href={loginHref}>Return to login</a>}
      </div>
    </div>
  );
}

/** For a page that has already read the session and is refusing the user itself: no lookup, the dashboard comes from the user in
 * hand. `accessUnavailable` is for the catch path, where there may be no session at all. */
export function accessDenied(user: User, message: string) {
  return <AccessUnavailableCard message={message} home={ROLE_DASHBOARD_PATH[user.role] ?? "/"} loginHref="/overseas/login" />;
}

/** Pages `return accessUnavailable(e)` from their own async body, so the lookup happens there and the page still resolves to plain
 * JSX (an async component inside JSX would not render in the page tests). */
export async function accessUnavailable(error: unknown, loginHref = "/overseas/login") {
  const message = error instanceof Error ? error.message : "Unable to load this workspace";
  let home: string | null = null;
  if (!(error instanceof ApiError && error.status === 401)) {
    try {
      const user = await serverApi<User>("/api/v1/auth/me");
      home = ROLE_DASHBOARD_PATH[user.role] ?? "/";
    } catch {
      home = null;
    }
  }
  return <AccessUnavailableCard message={message} home={home} loginHref={loginHref} />;
}
