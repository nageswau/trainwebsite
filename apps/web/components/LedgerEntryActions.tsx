"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { LEDGER_API, LEDGER_HOME, type LedgerEntry } from "@/lib/managementLedger";

type Step = "reject" | "reverse";
const CONFIRM: Record<Step, { label: string; button: string; done: string }> = {
  reject: { label: "Reason for rejecting", button: "Confirm rejection", done: "Entry rejected." },
  reverse: { label: "Reason for reversing", button: "Confirm reversal", done: "" },
};

// mgmt-004 (ML7-ML11): what the caller may do with this entry, from the API's own `can` flags. Approve and reject are a partner's
// (never on their own entry); reject and reverse ask for a reason first. Buttons are disabled while a request runs (no double submit).
export default function LedgerEntryActions({ entry }: { entry: LedgerEntry }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<Step | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);

  async function run(action: "submit" | "approve" | Step, done: string, body?: { reason: string }) {
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(`${LEDGER_API}/${entry.id}/${action}`, "POST", body);
    setBusy(false);
    if (!outcome.ok) {
      setResult({ text: outcome.message, failed: true });
      return;
    }
    setStep(null);
    setReason("");
    if (action === "reverse") {
      router.push(`${LEDGER_HOME}/${String(outcome.data.id)}`);
    } else {
      setResult({ text: done, failed: false });
    }
    router.refresh();
  }

  function confirm(kind: Step) {
    const text = reason.trim();
    if (text.length < 2 || text.length > 500) {
      setReasonError("Give a reason (2-500 characters)");
      return;
    }
    setReasonError("");
    void run(kind, CONFIRM[kind].done, { reason: text });
  }

  const { can } = entry;
  const any = can.edit || can.submit || can.decide || can.reverse;
  if (!any && !result) return null; // QA-01: the confirmation stays after the refresh leaves no action
  return (
    <div className="action-card" style={{ display: "grid", gap: 12 }}>
      {any && <div className="actions">
        {can.edit && <Link className="btn secondary" href={`${LEDGER_HOME}/${entry.id}/edit`}>Edit</Link>}
        {can.submit && <button className="btn" type="button" disabled={busy} onClick={() => void run("submit", "Submitted for approval.")}>Submit for approval</button>}
        {can.decide && <button className="btn" type="button" disabled={busy} onClick={() => void run("approve", "Entry approved.")}>Approve</button>}
        {can.decide && <button className="btn secondary" type="button" disabled={busy} onClick={() => setStep("reject")}>Reject</button>}
        {can.reverse && <button className="btn secondary" type="button" disabled={busy} onClick={() => setStep("reverse")}>Reverse</button>}
      </div>}
      {step && (
        <div className="field">
          <label htmlFor="ledger-reason">{CONFIRM[step].label}</label>
          <textarea id="ledger-reason" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}
            aria-invalid={reasonError ? true : undefined} aria-describedby={reasonError ? "ledger-reason-error" : undefined} style={{ minHeight: 64 }} />
          {reasonError && <p className="form-error" id="ledger-reason-error">{reasonError}</p>}
          {step === "reverse" && <p className="muted" style={{ fontSize: 13 }}>A reversing entry dated today cancels this one once a partner approves it.</p>}
          <div className="actions">
            <button className="btn" type="button" disabled={busy} onClick={() => confirm(step)}>{CONFIRM[step].button}</button>
            <button className="btn ghost" type="button" disabled={busy} onClick={() => { setStep(null); setReasonError(""); }}>Cancel</button>
          </div>
        </div>
      )}
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
    </div>
  );
}
