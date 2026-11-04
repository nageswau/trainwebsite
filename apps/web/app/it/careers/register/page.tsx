import Link from "next/link";

import BrandLogoLink from "@/components/BrandLogoLink";
import CandidateRegisterForm from "@/components/CandidateRegisterForm";

// hrc-022 (DEC-SCOPE-385 C2): an external job seeker's own account. IT students keep their student portal.
export default function CandidateRegisterPage() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <BrandLogoLink />
        <Link href="/it/careers" className="muted">← Back to careers</Link>
        <h2 style={{ marginTop: 22 }}>Create a candidate account</h2>
        <p className="muted">Keep your profile current for EduSphere recruiters. We&apos;ll email you a link to verify your address before you sign in.</p>
        <CandidateRegisterForm />
        <p className="muted" style={{ marginTop: 18 }}>
          Already registered? <Link href="/it/login" style={{ color: "var(--blue)", fontWeight: 800 }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}
