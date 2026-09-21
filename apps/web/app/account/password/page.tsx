import Link from "next/link";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import PublicShell from "@/components/PublicShell";
import { serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-006: like /account/privacy (SEC-002), this belongs to no one role's portal nav (`PORTAL_NAV`), so it is one shared
// route. Unlike that page it renders inside PublicShell (site header, footer) and links back to the role's dashboard, so
// it is never a dead end. It gates itself: /account/* is outside middleware.ts's matcher, and the API re-checks the
// session on every request regardless.
const NEXT = encodeURIComponent("/account/password");

export default async function AccountPasswordPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch {
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
          <Link href={ROLE_DASHBOARD_PATH[user.role] || "/"} className="muted">← Back to dashboard</Link>
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
