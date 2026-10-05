import Link from "next/link";
import { serverApi } from "@/lib/api";
import EmployerJobsPanel from "@/components/EmployerJobsPanel";
import EmployerCandidateSearchPanel from "@/components/EmployerCandidateSearchPanel";
import EmployerInterviewsPanel from "@/components/EmployerInterviewsPanel";

type EmployerProfile = {
  full_name: string;
  email: string;
  phone: string | null;
  company_name: string;
  company_website: string | null;
  registration_status: string | null;
};

// EMP-001: the Employer role has no PORTAL_NAV sections of its own yet, so this is a
// standalone page rather than the generic PortalPage shell every other role uses.
// EMP-002 added real job posting; EMP-003 added candidate search, both below.
export default async function EmployerDashboardPage() {
  let profile: EmployerProfile;
  try {
    profile = await serverApi<EmployerProfile>("/api/v1/employer/profile");
  } catch {
    return (
      <div className="section">
        <div className="container card">
          <h1>Sign in required</h1>
          <p className="muted">You need to sign in with an Employer account to view this page.</p>
          <a className="btn" href="/it/login">Sign in</a>
        </div>
      </div>
    );
  }
  return (
    <div className="section">
      <div className="container">
        <h1>Welcome, {profile.company_name}</h1>
        <p className="muted">Signed in as {profile.full_name} ({profile.email}).</p>
        {/* ENH-006: this page has no PortalShell or site header, so it needs its own way to the change-password page. */}
        <p><Link className="btn secondary small" href="/account/password">Change password</Link></p>
        <div className="action-card">
          <h3>Company profile</h3>
          <p><strong>Company:</strong> {profile.company_name}</p>
          <p><strong>Website:</strong> {profile.company_website || "—"}</p>
          <p className="muted" role="status">
            {profile.registration_status ? `Status: ${profile.registration_status}` : "Your account is active."}
          </p>
        </div>
        <div style={{ marginTop: 24 }}>
          <EmployerJobsPanel />
        </div>
        <div style={{ marginTop: 24 }}>
          <EmployerCandidateSearchPanel />
        </div>
        <div style={{ marginTop: 24 }}>
          <EmployerInterviewsPanel />
        </div>
      </div>
    </div>
  );
}
