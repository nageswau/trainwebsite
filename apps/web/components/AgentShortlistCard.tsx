"use client";

import type { ShortlistEntry } from "@/lib/agentShortlist";

// AGN-007: one shortlist entry card (spec §6.4: the confirm's Cancel has focus; Escape closes only the confirm).
export const editId = (id: string) => `shortlist-edit-${id}`;
export const removeId = (id: string) => `shortlist-remove-${id}`;

export default function ShortlistCard({ e, writable, confirming, removing, onEdit, onAskRemove, onCancelRemove, onRemove }: {
  e: ShortlistEntry; writable: boolean; confirming: boolean; removing: boolean; onEdit: () => void; onAskRemove: () => void; onCancelRemove: () => void; onRemove: () => void;
}) {
  const name = e.university.name;
  return (
    <li className="card">
      <strong>{name}</strong> {e.university.source === "agency" && <span className="badge">Agency</span>}
      <p className="muted">
        <span>{e.university.country ?? "—"}</span>
        {e.course && <> · <span>{e.course.title}</span></>}
      </p>
      {e.intake && <p>Intake: {e.intake}</p>}
      {e.tuition_fee && <p>Tuition fee: {e.tuition_fee}</p>}
      {e.entry_requirements && (
        <details>
          <summary>Entry requirements</summary>
          <p style={{ whiteSpace: "pre-line" }}>{e.entry_requirements}</p>
        </details>
      )}
      {writable &&
        (confirming ? (
          <span
            role="group"
            aria-label={`Confirm remove ${name}`}
            onKeyDown={(k) => {
              if (k.key === "Escape") {
                k.stopPropagation(); // the detail panel closes on Escape too; only the confirm closes here
                onCancelRemove();
              }
            }}
          >
            <button type="button" className="btn small" disabled={removing} onClick={onRemove}>Confirm remove</button>{" "}
            <button type="button" className="btn secondary small" autoFocus onClick={onCancelRemove}>Cancel</button>
          </span>
        ) : (
          <>
            <button id={editId(e.id)} type="button" className="btn secondary small" aria-label={`Edit ${name}`} onClick={onEdit}>Edit</button>{" "}
            <button id={removeId(e.id)} type="button" className="btn secondary small" aria-label={`Remove ${name}`} onClick={onAskRemove}>Remove</button>
          </>
        ))}
    </li>
  );
}
