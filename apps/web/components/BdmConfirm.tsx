"use client";
import type { KeyboardEvent, ReactNode } from "react";

// bdm-002: the inline confirm group used for archive, contact delete and reassign (the codebase has no dialog library). The confirm
// button takes focus; Escape cancels; the caller decides where focus goes after either answer.
export default function BdmConfirm({
  label,
  confirmText,
  cancelText = "Cancel",
  busyText,
  busy,
  className,
  onConfirm,
  onCancel,
  children,
}: {
  label: string;
  confirmText: string;
  cancelText?: string;
  busyText: string;
  busy: boolean;
  className?: string;
  onConfirm: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  return (
    <div role="group" aria-label={label} className={className} onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && onCancel()}>
      <p style={{ margin: 0 }}>{children}</p>
      <div className="actions">
        <button type="button" className="btn small" autoFocus onClick={onConfirm} disabled={busy}>
          {busy ? busyText : confirmText}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          {cancelText}
        </button>
      </div>
    </div>
  );
}
