import Link from "next/link";
import ForgotPasswordForm from "@/components/ForgotPasswordForm";

export default function ITForgotPassword() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/it/login" className="muted">← Back to sign in</Link>
        <h2 style={{ marginTop: 22 }}>Reset your password</h2>
        <p className="muted">Enter the email on your IT Training account and we&apos;ll send reset instructions.</p>
        <ForgotPasswordForm />
      </div>
    </div>
  );
}
