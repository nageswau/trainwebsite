"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { type AgentKycDoc, KYC_ACCEPT, KYC_DOCS, REGISTRATION_URL, STATUS_LABEL, checkKycFile } from "@/lib/agentKyc";
import { sendRequest } from "@/lib/apiErrors";

type Registration = { org: { name: string; status: string; kyc_required: boolean }; documents: AgentKycDoc[] };

// AGN-024 (DEC-SCOPE-224 K5): the one page a pending agency's Master can use -- each KYC document's status, the reason for a
// rejection, and a re-upload for rejected documents. Everything else in the agent portal stays blocked until approval.
export default function AgentRegistrationStatus() {
  const router = useRouter();
  const routerRef = useRef(router); // keep `load` stable so the effect below runs once, whatever the router's identity
  routerRef.current = router;
  const [data, setData] = useState<Registration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, { text: string; ok: boolean }>>({});
  const cards = useRef<Record<string, HTMLLIElement | null>>({});

  const load = useCallback(async () => {
    const outcome = await sendRequest(REGISTRATION_URL, { method: "GET" });
    if (!outcome.ok) { setError(outcome.message); return; }
    const value = outcome.data as unknown as Registration;
    if (value.org.status === "active") { routerRef.current.replace("/overseas/agent/dashboard"); return; }
    setError(null);
    setData(value);
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function reupload(event: FormEvent<HTMLFormElement>, doc: AgentKycDoc) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const input = formEl.elements.namedItem("file") as HTMLInputElement | null;
    const file = input?.files?.[0] ?? null;
    const note = (text: string, ok: boolean) => setNotes((n) => ({ ...n, [doc.doc_type]: { text, ok } }));
    const problem = checkKycFile(doc.label, file);
    if (problem) { note(problem, false); return; }
    const body = new FormData();
    body.append("file", file as File);
    const number = (formEl.elements.namedItem("doc_number") as HTMLInputElement | null)?.value.trim();
    if (number) body.append("doc_number", number);
    setBusy(doc.doc_type);
    const outcome = await sendRequest(`${REGISTRATION_URL}/documents/${doc.doc_type}/file`, { method: "PUT", body });
    setBusy(null);
    if (outcome.ok) {
      note(`${doc.label} uploaded. It will be reviewed again.`, true);
      await load();
      cards.current[doc.doc_type]?.focus();
    } else {
      note(outcome.message, false);
      if (outcome.status === 409) await load();
    }
  }

  if (error && !data) return <p className="form-error" role="alert">{error}</p>;
  if (!data) return <p className="muted">Loading your registration…</p>;
  const rejectedOrg = data.org.status === "rejected";
  return (
    <div className="card">
      <h1 style={{ fontSize: "1.4rem" }}>{rejectedOrg ? "Registration rejected" : "Registration status"}</h1>
      <p>{data.org.name}</p>
      <p className="muted">
        {rejectedOrg
          ? "Your agency's registration was not approved. Contact EduSphere Overseas Admin if you think this is a mistake."
          : "EduSphere is reviewing your registration. You can use the agent portal once your agency is approved."}
      </p>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!data.org.kyc_required ? null : (
        <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
          {data.documents.map((doc) => {
            const spec = KYC_DOCS.find((d) => d.type === doc.doc_type);
            const canReplace = doc.status === "rejected" && !rejectedOrg && !!spec;
            const note = notes[doc.doc_type];
            return (
              <li key={doc.id} ref={(el) => { cards.current[doc.doc_type] = el; }} tabIndex={-1} className="card" style={{ overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <strong>{doc.label}</strong> <span>{doc.doc_number_display}</span> <span className="badge">{STATUS_LABEL[doc.status]}</span>
                </div>
                {doc.status === "rejected" && doc.rejection_reason && <p style={{ fontSize: 13 }}>Reason: {doc.rejection_reason}</p>}
                {canReplace && spec && (
                  <form onSubmit={(e) => reupload(e, doc)} style={{ display: "grid", gap: 8, marginTop: 8 }}>
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`kyc-file-${doc.doc_type}`}>New {doc.label} file (PDF, JPG or PNG, max 5 MB)</label>
                      <input id={`kyc-file-${doc.doc_type}`} name="file" type="file" accept={KYC_ACCEPT} required />
                    </div>
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`kyc-number-${doc.doc_type}`}>Corrected {spec.numberLabel} (optional)</label>
                      <input id={`kyc-number-${doc.doc_type}`} name="doc_number" pattern={spec.pattern} maxLength={spec.maxLength} inputMode={spec.inputMode} autoComplete="off" />
                    </div>
                    <button className="btn small" disabled={busy === doc.doc_type} aria-label={`Upload new ${doc.label}`}>{busy === doc.doc_type ? "Uploading…" : "Upload"}</button>
                  </form>
                )}
                {note && (note.ok
                  ? <div role="status" aria-live="polite" style={{ fontSize: 13 }}>{note.text}</div>
                  : <div role="alert" className="form-error" style={{ fontSize: 13 }}>{note.text}</div>)}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
