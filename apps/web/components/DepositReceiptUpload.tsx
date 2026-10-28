"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { FILE_ACCEPT } from "@/lib/agentDocuments";
import { sendRequest } from "@/lib/apiErrors";

type Props = { applicationId: string; university: string; replacing: boolean };

// ccrm-048 (DEC-SCOPE-321): the Finance tab's deposit card -- the counselor (their application) or the Overseas Admin uploads the deposit
// receipt; the route stores it and attaches it to the deposit record in one step. One upload at a time.
export default function DepositReceiptUpload({ applicationId, university, replacing }: Props) {
  const router = useRouter();
  const inputId = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const action = replacing ? "Replace receipt" : "Upload receipt";

  async function upload() {
    if (inFlight.current) return;
    const file = fileInput.current?.files?.[0];
    if (!file) return setMessage({ text: "Choose a PDF, JPEG or PNG file first.", failed: true });
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    const outcome = await sendRequest(`/api/v1/workflows/overseas/applications/${encodeURIComponent(applicationId)}/deposit/receipt`, { method: "POST", body: form });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Receipt uploaded. The student can see it in their Documents.", failed: false });
    if (fileInput.current) fileInput.current.value = "";
    router.refresh();
  }

  return (
    <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>
          {message.text}
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <label htmlFor={inputId} className="visually-hidden">
          Deposit receipt file for {university}
        </label>
        <input id={inputId} ref={fileInput} type="file" accept={FILE_ACCEPT} style={{ maxWidth: "100%" }} />
        <button type="button" className="btn small" disabled={busy} onClick={upload}>
          {busy ? "Uploading…" : action}
          <span className="visually-hidden"> for {university}</span>
        </button>
      </div>
      <p className="muted" style={{ margin: 0 }}>PDF, JPEG or PNG, up to 20 MB.</p>
    </div>
  );
}
