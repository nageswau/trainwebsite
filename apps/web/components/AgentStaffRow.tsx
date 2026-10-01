"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { STAFF_URL, type StaffMember, staffFailure } from "@/lib/agentStaff";
import { sendJson } from "@/lib/apiErrors";

type Mode = "view" | "edit" | "confirm-deactivate" | "confirm-reset";
// One row action: `path` below the member's URL, the control that gets focus after success, the announced result, and whether
// the request carried typed values (then a dropped connection says the entry is kept).
type Action = { path?: string; method?: "POST" | "PATCH"; body?: unknown; keepsEntry?: boolean; focusNext: string; message: string | ((data: Record<string, unknown>) => string) };

function badge(m: StaffMember): string | null {
  if (m.status === "deactivated") return "Deactivated";
  if (m.setup === "link_expired") return "Link expired";
  return m.setup === "pending_setup" ? "Set-up pending" : null;
}

function InlineConfirm({ label, name, text, busy, onConfirm, onCancel }: { label: string; name: string; text: string; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    // Browser QA-04: Escape cancels, as in Edit.
    <div role="group" aria-label={`${label} ${name}`} style={{ marginTop: 8 }} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <p style={{ fontSize: 13 }}>{text}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" autoFocus disabled={busy} onClick={onConfirm}>{busy ? "Working…" : label}</button>
        <button className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// AGN-002: one staff member with its actions. Confirmations are inline (AgentTeamPanel's pattern): focus goes to Confirm; Cancel
// and Escape return it to the button that opened them, and a successful action moves it to the row's next logical
// control (which may only appear once the parent reloads the row). Server messages (409/429) show in the row's status region.
export default function AgentStaffRow({ member, onChanged }: { member: StaffMember; onChanged: (message: string) => void }) {
  const [mode, setMode] = useState<Mode>("view");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const returnFocusTo = useRef<string | null>(null);
  const id = (action: string) => `staff-${action}-${member.id}`;
  const who = `${member.code} ${member.full_name}`;

  // Re-tried when the row's data changes: after a deactivation the Reactivate button only exists once the parent has reloaded.
  useEffect(() => {
    if (mode !== "view" || !returnFocusTo.current) return;
    const target = document.getElementById(returnFocusTo.current);
    if (target) {
      target.focus();
      returnFocusTo.current = null;
    }
  }, [mode, member.status, member.setup]);

  function close(action: string) {
    returnFocusTo.current = id(action);
    setError(null);
    setMode("view");
  }

  async function run({ path = "", method = "POST", body = {}, keepsEntry = false, focusNext, message }: Action) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(`${STAFF_URL}/${member.id}${path}`, method, body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setError(staffFailure(outcome, keepsEntry));
      return;
    }
    returnFocusTo.current = id(focusNext);
    setMode("view");
    onChanged(typeof message === "string" ? message : message(outcome.data));
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const phone = String(data.get("phone") ?? "").trim();
    run({ method: "PATCH", body: { full_name: String(data.get("full_name") ?? ""), phone: phone || null }, keepsEntry: true, focusNext: "edit", message: `${member.code} updated.` });
  }

  const label = badge(member);
  const active = member.status === "active";

  return (
    <li className="card" style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
      <strong>{member.code}</strong> {member.full_name} <span className="muted" style={{ fontSize: 13 }}>{member.email}{member.phone && <> · <span style={{ whiteSpace: "nowrap" }}>{member.phone}</span></>}</span> {label && <span className="badge">{label}</span>}
      {mode === "edit" && (
        <form className="form" onSubmit={save} onKeyDown={(e) => e.key === "Escape" && close("edit")} aria-label={`Edit ${member.full_name}`} style={{ marginTop: 8 }}>
          <div className="field"><label htmlFor={id("name")}>Full name</label><input id={id("name")} name="full_name" defaultValue={member.full_name} maxLength={160} required autoFocus /></div>
          <div className="field"><label htmlFor={id("phone")}>Phone (optional)</label><input id={id("phone")} name="phone" type="tel" defaultValue={member.phone ?? ""} maxLength={40} /></div>
          <p className="muted" style={{ fontSize: 13 }}>Email can&apos;t be changed.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => close("edit")}>Cancel</button>
          </div>
        </form>
      )}
      {mode === "confirm-deactivate" && (
        <InlineConfirm
          label="Confirm deactivate" name={member.full_name} busy={busy} onCancel={() => close("deactivate")}
          text={`Deactivate ${member.full_name}? They will be signed out and can no longer sign in.`}
          onConfirm={() => run({ path: "/deactivate", focusNext: "reactivate", message: `${who} deactivated. They have been signed out.` })}
        />
      )}
      {mode === "confirm-reset" && (
        <InlineConfirm
          label="Confirm reset" name={member.full_name} busy={busy} onCancel={() => close("reset")}
          text={`Reset ${member.full_name}'s login? Their password stops working, they are signed out, and a new set-password link is emailed to them.`}
          onConfirm={() =>
            run({
              path: "/reset",
              focusNext: "reset",
              message: (data) =>
                data.email_status === "sent" ? `A new set-password link was emailed to ${member.full_name}.` : `${member.full_name}'s login was reset, but the email was not delivered. Try Reset again in a minute.`,
            })
          }
        />
      )}
      {mode === "view" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          <button id={id("edit")} className="btn secondary small" aria-label={`Edit ${member.full_name}`} onClick={() => setMode("edit")}>Edit</button>
          {active ? (
            <>
              <button id={id("reset")} className="btn secondary small" aria-label={`Reset ${member.full_name}`} onClick={() => setMode("confirm-reset")}>Reset</button>
              <button id={id("deactivate")} className="btn secondary small" aria-label={`Deactivate ${member.full_name}`} onClick={() => setMode("confirm-deactivate")}>Deactivate</button>
            </>
          ) : (
            <button
              id={id("reactivate")} className="btn secondary small" aria-label={`Reactivate ${member.full_name}`} disabled={busy}
              onClick={() => run({ path: "/reactivate", focusNext: "deactivate", message: `${who} reactivated.${member.setup ? " They have not set a password yet: use Reset to send a new link." : ""}` })}
            >
              {busy ? "Working…" : "Reactivate"}
            </button>
          )}
        </div>
      )}
      {/* Always mounted so screen readers announce an error when it arrives; styled only while it has something to say. */}
      <div data-testid={`staff-row-status-${member.id}`} className={error ? "form-error" : undefined} role="status" aria-live="polite" style={error ? { marginTop: 8, fontSize: 13 } : undefined}>{error}</div>
    </li>
  );
}
