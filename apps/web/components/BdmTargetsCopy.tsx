"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson } from "@/lib/apiErrors";
import { COPY_URL, monthLabel, previousMonth } from "@/lib/bdmTargets";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-016 (R8): copy last month's targets of the team into this month -- only targets not set yet; nothing is overwritten.
export default function BdmTargetsCopy({ month }: { month: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const from = monthLabel(previousMonth(month));

  async function copy() {
    setBusy(true);
    setError(null);
    const outcome = await sendJson(COPY_URL, "POST", { month });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      setError(outcome.message);
      focus("targets-copy-error");
      return;
    }
    const copied = Number((outcome.data as { copied?: number }).copied ?? 0);
    setNotice(copied === 0 ? `Nothing to copy: every target from ${from} is already set or there were none.` : `Copied ${copied} ${copied === 1 ? "target" : "targets"}.`);
    focus("targets-copy-status");
    router.refresh();
  }

  return (
    <section className="action-card wide" aria-label="Copy last month's targets">
      {confirming ? (
        <BdmConfirm label="Confirm copying last month's targets" confirmText="Yes, copy" busyText="Copying…" busy={busy} onConfirm={() => void copy()}
          onCancel={() => { setConfirming(false); focus("targets-copy"); }}>
          Copy your team&apos;s targets from {from} into {monthLabel(month)}? Targets already set for {monthLabel(month)} are kept.
        </BdmConfirm>
      ) : (
        <div className="actions">
          <button id="targets-copy" type="button" className="btn secondary" onClick={() => { setConfirming(true); setNotice(null); }}>Copy last month&apos;s targets</button>
        </div>
      )}
      <div id="targets-copy-status" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {error && <p id="targets-copy-error" tabIndex={-1} className="form-error" role="alert">{error}</p>}
    </section>
  );
}
