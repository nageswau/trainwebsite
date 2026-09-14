import Link from "next/link";
import { Suspense } from "react";
import ResetPasswordForm from "@/components/ResetPasswordForm";

export default function ITResetPassword() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/it/login" className="muted">← Back to sign in</Link>
        <h2 style={{ marginTop: 22 }}>Choose a new password</h2>
        <Suspense fallback={null}>
          <ResetPasswordForm division="it" />
        </Suspense>
      </div>
    </div>
  );
}
