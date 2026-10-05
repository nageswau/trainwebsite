"use client";

// AGN-001 browser QA-02: a way out of "Access unavailable" for a signed-in user. A full navigation (not the app router) so the
// card stays usable from server-rendered pages and no stale client state survives the sign-out. Leaves even if the call fails:
// the user asked to leave, and the login page will show whether a session is still live.
export default function SignOutButton({ redirectTo }: { redirectTo: string }) {
  async function signOut() {
    try {
      await fetch("/api/v1/auth/logout", { method: "POST" });
    } catch {
      // fall through to the login page
    }
    window.location.assign(redirectTo);
  }

  return (
    <button type="button" className="btn secondary" onClick={signOut}>
      Sign out
    </button>
  );
}
