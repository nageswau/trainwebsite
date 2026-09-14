import DataPrivacyPanel from "@/components/DataPrivacyPanel";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";

// SEC-002: self-service data export/delete is "All roles" -- it does not belong to any
// one role's portal nav (`PORTAL_NAV`), so it lives at a single shared route reachable
// from `HeaderAuthActions` regardless of division/role, rather than duplicated across
// ten role-specific navigation arrays.
export default async function AccountPrivacyPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch {
    return (
      <div className="section">
        <div className="container card">
          <h1>Sign in required</h1>
          <p className="muted">You need to be signed in to manage your data.</p>
          <div className="field" style={{ flexDirection: "row", gap: 12 }}>
            <a className="btn" href="/it/login">IT Training sign in</a>
            <a className="btn secondary" href="/overseas/login">Overseas Education sign in</a>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="section">
      <div className="container">
        <h1>Privacy &amp; your data</h1>
        <p className="muted">Signed in as {user.full_name} ({user.email}).</p>
        <DataPrivacyPanel />
      </div>
    </div>
  );
}
