"use client";

import { useId, useRef, useState } from "react";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { detailMessage } from "@/lib/apiErrors";

const EXPIRED = "Your session has expired. Sign in again.";
const FAILED = "Something went wrong on our side. Please try again.";

// ENH-015: downloads a server-generated PDF report. Fetched first rather than linked (<a download>), so a refusal or a
// server error is shown as a message instead of being saved as a file; only a real application/pdf response is saved.
// The button stays in place and keeps focus; the outcome is announced under it (FormMessage). `hint` (QA15-10): the PDF is
// untagged, so the page says where the same information can be read with a screen reader; it is the button's description.
export default function ReportDownloadButton({ url, label, filename, hint }: { url: string; label: string; filename: string; hint?: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const downloading = useRef(false);
  const hintId = useId();

  async function download() {
    if (downloading.current) return;
    downloading.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (response.ok && response.headers.get("content-type")?.startsWith("application/pdf")) {
        save(await response.blob(), filename);
        setMessage({ text: "Report downloaded.", failed: false });
      } else {
        setMessage({ text: await failureText(response), failed: true });
      }
    } catch {
      setMessage({ text: FAILED, failed: true });
    } finally {
      downloading.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="report-download">
      <div className="actions">
        {/* aria-disabled, not `disabled`: a disabled button drops keyboard focus to <body> (QA15-01). The `downloading`
            guard is what stops a second request; globals.css dims `.btn[aria-disabled="true"]` like `.btn:disabled`. */}
        <button type="button" className="btn" onClick={download} aria-disabled={busy} aria-busy={busy} aria-describedby={hint ? hintId : undefined}>
          {busy ? "Preparing PDF…" : label}
        </button>
      </div>
      {hint && <p id={hintId} className="muted report-hint">{hint}</p>}
      {message && <FormMessage message={message} />}
    </div>
  );
}

async function failureText(response: Response): Promise<string> {
  if (response.status === 401) return EXPIRED;
  if (response.ok || response.status >= 500) return FAILED;
  const body = await response.json().catch(() => ({}));
  return detailMessage((body as { detail?: unknown }).detail, FAILED);
}

function save(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked on the next tick: revoking synchronously can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(href), 0);
}
