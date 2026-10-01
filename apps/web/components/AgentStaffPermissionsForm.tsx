"use client";

import { FormEvent } from "react";

import type { AgentPermissions } from "@/lib/types";

const OPTIONS: { key: keyof AgentPermissions; label: string; hint: string }[] = [
  { key: "can_verify_documents", label: "Verify documents", hint: "Mark pending documents as verified. Only Masters can reject or request changes." },
  { key: "can_view_reports", label: "View reports", hint: "See the agency's application summary." },
];

// AGN-003 (DEC-SCOPE-044 P1/P2): what one staff member may do beyond the student journey. Native checkboxes in the ENH-025
// form-section fieldset; each hint is tied to its box (aria-describedby). The row owns the request, busy state and errors.
export default function AgentStaffPermissionsForm({ idPrefix, name, value, busy, onSave, onCancel }: {
  idPrefix: string; name: string; value: AgentPermissions; busy: boolean; onSave: (next: AgentPermissions) => void; onCancel: () => void;
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSave({ can_verify_documents: data.get("can_verify_documents") === "on", can_view_reports: data.get("can_view_reports") === "on" });
  }

  return (
    <form className="form" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()} aria-label={`Permissions for ${name}`} style={{ marginTop: 8 }}>
      <fieldset className="form-section">
        <legend>What {name} can do</legend>
        {OPTIONS.map(({ key, label, hint }, index) => (
          <div key={key} className="field">
            <label htmlFor={`${idPrefix}-${key}`} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input id={`${idPrefix}-${key}`} name={key} type="checkbox" defaultChecked={value[key]} aria-describedby={`${idPrefix}-${key}-hint`} autoFocus={index === 0} style={{ width: "auto" }} />
              {label}
            </label>
            <p id={`${idPrefix}-${key}-hint`} className="muted" style={{ fontSize: 13, margin: 0 }}>{hint}</p>
          </div>
        ))}
      </fieldset>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
