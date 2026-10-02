"use client";

import type { AgentUniversity } from "@/lib/agentShortlist";

// AGN-007: one agency university card (spec §6.4: the confirm's Cancel has focus; Escape closes only the confirm).
export const editId = (id: string) => `agent-uni-edit-${id}`;
export const deleteId = (id: string) => `agent-uni-del-${id}`;

export default function AgentUniversityCard({ u, actionable, confirming, removing, error, onEdit, onAskDelete, onCancelDelete, onDelete }: {
  u: AgentUniversity; actionable: boolean; confirming: boolean; removing: boolean; error: string | null;
  onEdit: () => void; onAskDelete: () => void; onCancelDelete: () => void; onDelete: () => void;
}) {
  return (
    <li className="card">
      <h3>{u.name}</h3>
      <p className="muted">{[u.country, u.city].filter(Boolean).join(" · ")}</p>
      {u.entry_requirements && (
        <details>
          <summary>Entry requirements</summary>
          <p style={{ whiteSpace: "pre-line" }}>{u.entry_requirements}</p>
        </details>
      )}
      {actionable &&
        (confirming ? (
          <span
            role="group"
            aria-label={`Confirm delete ${u.name}`}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.stopPropagation();
                onCancelDelete();
              }
            }}
          >
            <button type="button" className="btn small" disabled={removing} onClick={onDelete}>
              Confirm delete
            </button>{" "}
            <button type="button" className="btn secondary small" autoFocus onClick={onCancelDelete}>
              Cancel
            </button>
          </span>
        ) : (
          <>
            <button type="button" id={editId(u.id)} className="btn secondary small" aria-label={`Edit ${u.name}`} onClick={onEdit}>
              Edit
            </button>{" "}
            <button type="button" id={deleteId(u.id)} className="btn secondary small" aria-label={`Delete ${u.name}`} onClick={onAskDelete}>
              Delete
            </button>
          </>
        ))}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}
