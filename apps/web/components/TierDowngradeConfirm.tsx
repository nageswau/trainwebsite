"use client";

import { useEffect, useRef } from "react";

export type TierService = { key: string; label: string };

// ENH-023 (DEC-SCOPE-029 D7): the inline downgrade confirmation, in the ENH-004/ENH-005 pattern (SchoolPromotionPanel,
// AdminTransferRow) -- no dialog library. The consequences are a list, Confirm takes focus when the block appears and is
// described by them, and Escape or Cancel hands control back to the panel, which returns focus to Save.
export default function TierDowngradeConfirm({ schoolName, fromTier, toTier, lost, busy, onConfirm, onCancel }: {
  schoolName: string; fromTier: string; toTier: string; lost: TierService[]; busy: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);
  return (
    <div className="form-warning" role="group" aria-labelledby="tier-downgrade-title" onKeyDown={(e) => { if (e.key === "Escape" && !busy) onCancel(); }}>
      <p id="tier-downgrade-title"><strong>Downgrading {schoolName} from {fromTier} to {toTier}.</strong></p>
      <div id="tier-downgrade-consequences">
        <p>These services will no longer be available for new work:</p>
        <ul>{lost.map((s) => <li key={s.key}>{s.label}</li>)}</ul>
        <p>Work already started can still be completed. The school will be notified.</p>
      </div>
      <div className="actions">
        <button ref={confirmRef} type="button" className="btn" disabled={busy} aria-describedby="tier-downgrade-consequences" onClick={onConfirm}>{busy ? "Saving…" : "Confirm downgrade"}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
