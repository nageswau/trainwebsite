"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { KYC_ACCEPT, KYC_DOCS, REGISTRATION_STATUS_PATH, checkKycFile } from "@/lib/agentKyc";

function detail(value: unknown) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Registration failed.";
}

// AGN-001 (E2): an education agent may name their agency; blank falls back to their full name on the server.
// AGN-024 (DEC-SCOPE-224 K1/K2/K8): an agent also uploads PAN card, Aadhaar card and business licence, sent as multipart.
export default function RegisterForm({ division }: { division: "it" | "overseas" }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [accountType, setAccountType] = useState("student");
  const isAgent = division === "overseas" && accountType === "agent";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const agency = String(form.get("agency_name") || "").trim();
    const base = { full_name: form.get("full_name"), email: form.get("email"), phone: form.get("phone") || null, password: form.get("password"), division, account_type: isAgent ? "agent" : "student" };
    let init: RequestInit;
    if (isAgent) {
      const body = new FormData();
      for (const [key, value] of Object.entries(base)) if (value) body.append(key, String(value));
      if (agency) body.append("agency_name", agency);
      for (const doc of KYC_DOCS) {
        // Read the chosen file from the input itself: identical in browsers, and works with jsdom's overridden `files`.
        const input = formEl.elements.namedItem(doc.fileField) as HTMLInputElement | null;
        const file = input?.files?.[0] ?? null;
        const problem = checkKycFile(doc.label, file);
        if (problem) { setMessage(problem); return; }
        const number = String(form.get(doc.numberField) || "").trim();
        body.append(doc.numberField, doc.type === "pan" ? number.toUpperCase() : number);
        body.append(doc.fileField, file as File);
      }
      init = { method: "POST", body };
    } else {
      init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(base) };
    }
    setBusy(true);
    const response = await fetch("/api/v1/auth/register", init);
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setMessage(detail(data.detail)); return; }
    router.push(data.user.role === "agent" ? REGISTRATION_STATUS_PATH : division === "it" ? "/it/student/dashboard" : "/overseas/student/dashboard");
    router.refresh();
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field"><label htmlFor="reg-full-name">Full name</label><input id="reg-full-name" name="full_name" autoComplete="name" required /></div>
      <div className="field"><label htmlFor="reg-email">Email</label><input id="reg-email" name="email" type="email" autoComplete="email" required /></div>
      <div className="field"><label htmlFor="reg-phone">Phone</label><input id="reg-phone" name="phone" type="tel" autoComplete="tel" /></div>
      {division === "overseas" && (
        <div className="field">
          <label htmlFor="reg-account-type">Account type</label>
          <select id="reg-account-type" name="account_type" value={accountType} onChange={(e) => setAccountType(e.target.value)}>
            <option value="student">Student</option>
            <option value="agent">Education agent</option>
          </select>
        </div>
      )}
      {isAgent && <div className="field"><label htmlFor="reg-agency-name">Agency name (optional)</label><input id="reg-agency-name" name="agency_name" maxLength={160} autoComplete="organization" /></div>}
      {isAgent && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600 }}>Verification documents</legend>
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>Upload all three. PDF, JPG or PNG, up to 5 MB each. EduSphere checks them before approving your agency.</p>
          {KYC_DOCS.map((doc) => (
            <div key={doc.type} style={{ display: "grid", gap: 8, marginBottom: 12 }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor={`reg-${doc.numberField}`}>{doc.numberLabel}</label>
                <input id={`reg-${doc.numberField}`} name={doc.numberField} required pattern={doc.pattern} maxLength={doc.maxLength} inputMode={doc.inputMode} autoComplete="off" aria-describedby={doc.hint ? `reg-${doc.numberField}-hint` : undefined} />
                {doc.hint && <span id={`reg-${doc.numberField}-hint`} className="muted" style={{ fontSize: 12 }}>{doc.hint}</span>}
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor={`reg-${doc.fileField}`}>{doc.label} (PDF, JPG or PNG, max 5 MB)</label>
                <input id={`reg-${doc.fileField}`} name={doc.fileField} type="file" accept={KYC_ACCEPT} required />
              </div>
            </div>
          ))}
        </fieldset>
      )}
      <div className="field"><label htmlFor="reg-password">Password</label><input id="reg-password" name="password" type="password" minLength={10} autoComplete="new-password" required /><span className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span></div>
      {message && <div className="form-error" role="alert">{message}</div>}
      <button className="btn" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
    </form>
  );
}
