import type { Metadata } from "next";
import Link from "next/link";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-006: like /account/privacy (SEC-002), this belongs to no one role's portal nav (`PORTAL_NAV`), so it is one shared
// route. Unlike that page it renders inside PublicShell (site header, footer) and links back to the role's dashboard, so
// it is never a dead end. It gates itself: /account/* is outside middleware.ts's matcher, and the API re-checks the
// session on every request regardless.
const NEXT = encodeURIComponent("/account/password");

// The root layout adds " | EduSphere". A page of its own title lets a tab, history entry or screen reader say where the user is.
export const metadata: Metadata = { title: "Change your password" };

export default async function AccountPasswordPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (error) {
    // Only an explicit 401 means "signed out". An outage, a 5xx or a network failure must not be reported as that: following
    // "sign in" would lead to a login that fails too (browser QA, QA-002).
    if (!(error instanceof ApiError && error.status === 401)) {
      return (
        <PublicShell>
          <div className="section">
            <div className="container card">
              <h1>Temporarily unavailable</h1>
              <p className="muted">We can&apos;t reach EduSphere right now. Your password has not been changed. Try again in a moment.</p>
              <a className="btn" href="/account/password">Try again</a>
            </div>
          </div>
        </PublicShell>
      );
    }
    return (
      <PublicShell>
        <div className="section">
          <div className="container card">
            <h1>Sign in required</h1>
            <p className="muted">You need to be signed in to change your password.</p>
            <div className="actions">
              <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
              <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
            </div>
          </div>
        </div>
      </PublicShell>
    );
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 560 }}>
          <Link href={ROLE_DASHBOARD_PATH[user.role] || "/"} className="muted" style={{ display: "inline-block", padding: "6px 0" }}>← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Change your password</h1>
          <p className="muted">Signed in as {user.full_name} ({user.email}).</p>
          <div className="action-card">
            <ChangePasswordForm email={user.email} forgotPasswordHref={division ? `/${division}/forgot-password` : undefined} />
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
