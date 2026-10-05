import Link from "next/link";
import ForgotPasswordForm from "@/components/ForgotPasswordForm";

// bdm-001 QA-05 (owner, 2026-10-02): password recovery for the admin sign-in (Super Admins, BDM Managers and Telecaller Managers). Public (middleware);
// the request form is the shared one, and its development link resolves to /admin/reset-password.
export default function AdminForgotPassword() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/admin/login" className="muted">← Back to sign in</Link>
        <h2 style={{ marginTop: 22 }}>Reset your password</h2>
        <p className="muted">Enter the email on your administration or BDM Manager account and we&apos;ll send reset instructions.</p>
        <ForgotPasswordForm />
      </div>
    </div>
  );
}
