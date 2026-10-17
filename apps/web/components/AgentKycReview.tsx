"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { type AdminKycDoc, STATUS_LABEL, adminKycUrl } from "@/lib/agentKyc";
import { sendJson, sendRequest } from "@/lib/apiErrors";

// AGN-024 (DEC-SCOPE-224 K3): Overseas Admin / Super Admin check each KYC document of a pending agency -- View (streamed, audited),
// Verify, or Reject with a reason the agent is emailed. The panel's Approve stays disabled until all three are verified.
export default function AgentKycReview({ orgId, orgName, onChanged }: { orgId: string; orgName: string; onChanged: () => void }) {
  const [items, setItems] = useState<AdminKycDoc[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rows = useRef<Record<string, HTMLLIElement | null>>({});

  const load = useCallback(async () => {
    const outcome = await sendRequest(adminKycUrl(orgId), { method: "GET" });
    if (!outcome.ok) { setFailed(true); return; }
    setFailed(false);
    setItems((outcome.data as { items: AdminKycDoc[] }).items);
  }, [orgId]);

  useEffect(() => { void load(); }, [load]);

  async function decide(doc: AdminKycDoc, action: "verify" | "reject", reason?: string) {
    setBusy(doc.id); setNote(null); setError(null);
    const outcome = await sendJson(`${adminKycUrl(orgId)}/${doc.id}/${action}`, "POST", action === "reject" ? { reason } : {});
    setBusy(null);
    if (!outcome.ok) { setError(outcome.message); return; }
    setRejecting(null);
    setNote(`${doc.label} ${action === "verify" ? "verified" : "rejected"}.`);
    await load();
    rows.current[doc.id]?.focus();
    onChanged();
  }

  function submitReject(event: FormEvent<HTMLFormElement>, doc: AdminKycDoc) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") || "").trim();
    void decide(doc, "reject", reason);
  }

  if (failed) return <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load verification documents.</p>;
  if (items === null) return <p className="muted" style={{ fontSize: 13 }}>Loading verification documents…</p>;
  return (
    <section aria-label={`Verification documents for ${orgName}`} style={{ marginTop: 8 }}>
      <h6 style={{ margin: "8px 0", fontSize: 13 }}>Verification documents</h6>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {items.map((doc) => (
          <li key={doc.id} ref={(el) => { rows.current[doc.id] = el; }} tabIndex={-1} style={{ fontSize: 13, overflowWrap: "anywhere" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <strong>{doc.label}</strong> <span>{doc.doc_number}</span> <span className="badge">{STATUS_LABEL[doc.status]}</span>
            </div>
            {doc.status === "rejected" && doc.rejection_reason && <div className="muted">Reason: {doc.rejection_reason}</div>}
            {rejecting === doc.id ? (
              <form onSubmit={(e) => submitReject(e, doc)} style={{ display: "grid", gap: 6, marginTop: 6 }}>
                <label htmlFor={`kyc-reason-${doc.id}`}>Reason for rejecting {doc.label}</label>
                <textarea id={`kyc-reason-${doc.id}`} name="reason" required minLength={3} maxLength={500} rows={2} autoFocus />
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn small" disabled={busy === doc.id}>{busy === doc.id ? "Working…" : "Confirm reject"}</button>
                  <button type="button" className="btn secondary small" disabled={busy === doc.id} onClick={() => setRejecting(null)}>Cancel</button>
                </div>
              </form>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                <a className="btn secondary small" href={`${adminKycUrl(orgId)}/${doc.id}/file`} target="_blank" rel="noopener noreferrer" aria-label={`View ${doc.label} for ${orgName}`}>View</a>
                {doc.status !== "verified" && <button type="button" className="btn small" disabled={busy === doc.id} aria-label={`Verify ${doc.label} for ${orgName}`} onClick={() => decide(doc, "verify")}>Verify</button>}
                {doc.status !== "rejected" && <button type="button" className="btn secondary small" disabled={busy === doc.id} aria-label={`Reject ${doc.label} for ${orgName}`} onClick={() => setRejecting(doc.id)}>Reject</button>}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div role="status" aria-live="polite" style={{ fontSize: 13, marginTop: 6 }}>{note}</div>
      <div role="alert" className={error ? "form-error" : undefined} style={{ fontSize: 13, marginTop: 6 }}>{error}</div>
    </section>
  );
}
