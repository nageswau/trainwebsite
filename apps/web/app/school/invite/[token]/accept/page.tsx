import SchoolInviteAcceptForm from "@/components/SchoolInviteAcceptForm";

// SCH-003: turns an invite into a real, usable login in one step. Public until the
// token is validated server-side -- the resulting account's school_id is always the
// invite's own, never a value this page can influence (SCH-003-AC06).
export default async function SchoolInviteAcceptPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <h2 style={{ marginTop: 22 }}>Set up your EduSphere login</h2>
        <p className="muted">Choose a password to finish setting up the account your School Coordinator invited you to.</p>
        <SchoolInviteAcceptForm token={token} />
      </div>
    </div>
  );
}
