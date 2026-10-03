"use client";
import { useEffect, useRef } from "react";

import { type Overlap, whenText } from "@/lib/bdmAppointments";

// bdm-006 (A6, R-F7): the overlap warning, the bdm-002 duplicate-alert pattern. The matches are plain text (no links), so following one
// cannot lose the unsaved entry. Focus moves to the heading so a screen reader announces it.
export default function BdmOverlapAlert({ overlap, busy, onConfirm, onCancel }: { overlap: Overlap; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <div role="alert" className="action-card" onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <h4 ref={heading} tabIndex={-1} style={{ margin: "0 0 8px" }}>
        {overlap.message}
      </h4>
      <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
        {overlap.matches.map((m) => (
          <li key={m.id}>
            {m.code} · {whenText(m.starts_at, m.duration_minutes)} · {m.organization_name}
          </li>
        ))}
      </ul>
      {overlap.total > overlap.matches.length && <p className="muted">and {overlap.total - overlap.matches.length} more.</p>}
      <div className="actions">
        <button type="button" className="btn small" onClick={onConfirm} disabled={busy}>
          {busy ? "Saving…" : "Save anyway"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
