import Link from "next/link";
import { Suspense } from "react";
import ResetPasswordForm from "@/components/ResetPasswordForm";
import BrandLogoLink from "@/components/BrandLogoLink";

// bdm-001 QA-05 (owner, 2026-10-02): the admin portal's own reset page -- a BDM manager's set-password link opens here, so every
// link on the page stays on /admin. Public (middleware), and a static route wins over /admin/[module].
export default function AdminResetPassword() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <BrandLogoLink />
        <Link href="/admin/login" className="muted">← Back to sign in</Link>
        <h2 style={{ marginTop: 22 }}>Choose a new password</h2>
        <Suspense fallback={null}>
          <ResetPasswordForm division="admin" />
        </Suspense>
      </div>
    </div>
  );
}
