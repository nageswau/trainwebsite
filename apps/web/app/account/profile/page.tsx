import type { Metadata } from "next";
import Link from "next/link";
import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";
import ProfileForm from "@/components/ProfileForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import { isNotificationPreferences, type NotificationPreferences, type User } from "@/lib/types";

// Belongs to no one role's portal nav (PORTAL_NAV/SCHOOL_NAV), so it is one shared route, same
// reasoning as /account/password (ENH-006). Renders inside PublicShell (site header, footer) and
// links back to the role's dashboard, so it is never a dead end. Gates itself: /account/* is
// outside middleware.ts's matcher, and the API re-checks the session on every request regardless.
const NEXT = encodeURIComponent("/account/profile");

export const metadata: Metadata = { title: "Your profile" };

export default async function AccountProfilePage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (error) {
    // Only an explicit 401 means "signed out". An outage, a 5xx or a network failure must not be
    // reported as that -- following "sign in" would lead to a login that fails too.
    if (!(error instanceof ApiError && error.status === 401)) {
      return (
        <PublicShell>
          <div className="section">
            <div className="container card">
              <h1>Temporarily unavailable</h1>
              <p className="muted">We can&apos;t reach EduSphere right now. Your profile has not been changed. Try again in a moment.</p>
              <a className="btn" href="/account/profile">Try again</a>
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
            <p className="muted">You need to be signed in to view your profile.</p>
            <div className="actions">
              <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
              <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
            </div>
          </div>
        </div>
      </PublicShell>
    );
  }
  let preferences: NotificationPreferences | null = null;
  try {
    const loaded: unknown = await serverApi<unknown>("/api/v1/account/notification-preferences");
    preferences = isNotificationPreferences(loaded) ? loaded : null;
  } catch {
    preferences = null; // this section only; the profile form still renders
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 560 }}>
          <Link href={ROLE_DASHBOARD_PATH[user.role] || "/"} className="muted" style={{ display: "inline-block", padding: "6px 0" }}>← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Your profile</h1>
          <p className="muted">Signed in as {user.full_name} ({user.email}).</p>
          <div className="action-card">
            <ProfileForm fullName={user.full_name} phone={user.phone ?? null} />
          </div>
          <h2 style={{ fontSize: 24, marginTop: 28 }}>Notifications</h2>
          <p className="muted">Choose where we send updates about results, sessions and applications.</p>
          <div className="action-card">
            {preferences ? (
              <NotificationPreferencesForm initial={preferences} phone={user.phone ?? null} />
            ) : (
              <div className="form-error" role="alert">
                <p style={{ margin: 0 }}>We couldn&apos;t load your notification settings right now.</p>
                <p style={{ margin: "6px 0 0" }}>
                  <a href="/account/profile" style={{ color: "var(--blue)", fontWeight: 800 }}>Try again</a>
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
