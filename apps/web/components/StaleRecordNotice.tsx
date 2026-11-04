"use client";
import { useEffect, useRef } from "react";

import { type ReviewItem, type StaleConflict, staleSummary } from "@/lib/staleGuard";

// hrc-003 (DEC-SCOPE-370 S7): shown inside an edit form when its save was refused because someone else saved first. Reload drops the
// user's edits; Review my changes puts them back over the latest values and lists them here for checking before the user saves again.
// It takes focus when it appears, so keyboard and screen-reader users land on it.
const shown = (value: string) => (value.trim() ? (value.length > 80 ? `“${value.slice(0, 80)}…”` : `“${value}”`) : "empty");

export default function StaleRecordNotice({ guard, labelOf, display = (_key, value) => value, onReload, onReview }: {
  guard: { conflict: StaleConflict<unknown> | null; review: ReviewItem[] | null };
  labelOf: (field: string) => string;
  /** A value as the user reads it (an option's name rather than its id). */
  display?: (key: string, value: string) => string;
  onReload: () => void;
  onReview: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const { conflict, review } = guard;
  useEffect(() => {
    if (conflict || review) box.current?.focus();
  }, [conflict, review]);
  if (!conflict && !review) return null;

  return (
    <div ref={box} tabIndex={-1} role="alert" className="action-card" style={{ borderColor: "#d97706", gap: 8, padding: 14 }}>
      {conflict ? (
        <>
          <p style={{ margin: 0, fontWeight: 700 }}>{staleSummary(conflict)}</p>
          {conflict.changedFields.length > 0 && (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Changed: {conflict.changedFields.map(labelOf).join(", ")}.</p>
          )}
          <p style={{ margin: 0, fontSize: 13 }}>Your changes are not saved. Reload to see the latest version, or review your changes on top of it.</p>
          <div className="actions" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn small" onClick={onReview}>Review my changes</button>
            <button type="button" className="btn secondary small" onClick={onReload}>Reload latest</button>
          </div>
        </>
      ) : review!.length === 0 ? (
        <p style={{ margin: 0 }}>The form now shows the latest version. Your changes already match it, so there is nothing to save.</p>
      ) : (
        <>
          <p style={{ margin: 0, fontWeight: 700 }}>The form now shows the latest version with your changes put back. Check them, then save.</p>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }} aria-label="Your changes">
            {review!.map((item) => (
              <li key={item.key} style={{ overflowWrap: "anywhere" }}>
                <strong>{labelOf(item.key)}:</strong> yours {shown(display(item.key, item.yours))}, now on record {shown(display(item.key, item.now))}
                {item.alsoChanged && <span className="status pending" style={{ marginLeft: 6 }}>also changed by someone else</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
