import Link from "next/link";
import EmployerRegisterForm from "@/components/EmployerRegisterForm";

export default function EmployerRegisterPage() {
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/it/corporate-hiring" className="muted">← Back to Corporate Hiring</Link>
        <h2 style={{ marginTop: 22 }}>Register your company</h2>
        <p className="muted">Create an Employer account to post hiring requirements and review shortlisted candidates directly.</p>
        <EmployerRegisterForm />
        <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
          Already registered? <Link href="/it/login" style={{ color: "var(--blue)", fontWeight: 800 }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}
