import Link from "next/link";

import BrandLogoLink from "@/components/BrandLogoLink";
import CandidateVerifyEmail from "@/components/CandidateVerifyEmail";

// hrc-022 (DEC-SCOPE-385 C3): the link from a verification or email-change email. The token is used only when the person clicks.
export default async function CandidateVerifyEmailPage({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const raw = (await searchParams).token;
  const token = typeof raw === "string" ? raw : "";
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <BrandLogoLink />
        <Link href="/it/careers" className="muted">← Back to careers</Link>
        <h2 style={{ marginTop: 22 }}>Verify your email</h2>
        <p className="muted">Confirm that this email address is yours.</p>
        <CandidateVerifyEmail token={token} />
      </div>
    </div>
  );
}
