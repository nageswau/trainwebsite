"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { sendJson } from "@/lib/apiErrors";
import { isLead, type Lead, NOTE_MAX, orgLeadsUrl, possibleDuplicate, type PossibleDuplicate } from "@/lib/bdmLeads";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Draft = { name: string; email: string; phone: string; interest: string; note: string };
const EMPTY: Draft = { name: "", email: "", phone: "", interest: "", note: "" };
const FIELD_ORDER = ["name", "email", "phone", "interest", "note"] as const; // focus order after a refused save
const REQUIRED: [keyof Draft, string][] = [
  ["name", "Enter the student's name."], ["email", "Enter the student's email."], ["interest", "Enter what the student is interested in."],
];

// bdm-017 (spec §6): add one student lead to an organization (Q-14: one at a time). The API decides every rule; the client only checks
// the required fields. A possible duplicate (409) lists the matching leads and saves only when the BDM confirms (L8).
export default function BdmLeadForm({ organizationId, onSaved, onCancel }: { organizationId: string; onSaved: (lead: Lead) => void; onCancel: () => void }) {
  const idp = useId();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<PossibleDuplicate | null>(null);
  const [busy, setBusy] = useState(false);
  useLeaveGuard(JSON.stringify(draft) !== JSON.stringify(EMPTY) && !busy, "Discard this lead?");
  const focus = useFocusAfterRender();
  const fieldId = (name: string) => `${idp}-${name}`;
  useEffect(() => focus(fieldId("name")), []); // eslint-disable-line react-hooks/exhaustive-deps -- once, on open

  const set = (key: keyof Draft, value: string) => setDraft((d) => ({ ...d, [key]: value }));
  const errorId = (name: string) => `${idp}-${name}-error`;
  const err = (name: string) => (errors[name] ? <p id={errorId(name)} className="form-error">{errors[name]}</p> : null);
  const described = (name: string, hint?: string) => {
    const ids = [hint, errors[name] ? errorId(name) : undefined].filter(Boolean).join(" ");
    return { "aria-invalid": errors[name] ? true : undefined, "aria-describedby": ids || undefined };
  };
  const focusFirst = (found: Record<string, string>) => {
    const first = FIELD_ORDER.find((name) => found[name]);
    focus(first ? fieldId(first) : fieldId("message"));
  };

  async function save(acknowledge: boolean) {
    setBusy(true);
    setFailure(null);
    const body: Record<string, unknown> = {
      name: draft.name.trim(), email: draft.email.trim(), phone: draft.phone.trim() || null, interest: draft.interest.trim(), note: draft.note.trim() || null,
    };
    if (acknowledge) body.acknowledge_duplicate = true;
    const outcome = await sendJson(orgLeadsUrl(organizationId), "POST", body);
    setBusy(false);
    setDuplicate(null);
    if (outcome.ok && isLead(outcome.data)) return onSaved(outcome.data);
    if (outcome.ok) {
      setFailure("Unable to save this lead.");
      return focusFirst({});
    }
    const match = outcome.status === 409 ? possibleDuplicate(outcome.detail) : null;
    if (match) return setDuplicate(match); // BdmConfirm takes focus on "Save anyway"
    const mapped = fieldErrors(outcome.detail);
    setErrors(mapped);
    const unreadable = outcome.status !== undefined && (outcome.status >= 500 || (typeof outcome.detail !== "string" && !Array.isArray(outcome.detail)));
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : unreadable ? "The server couldn't save this lead. Your entry is kept — try again." : outcome.message);
    focusFirst(mapped);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    for (const [key, message] of REQUIRED) if (!draft[key].trim()) local[key] = message;
    setErrors(local);
    if (Object.keys(local).length) {
      setFailure("Check the highlighted fields.");
      return focusFirst(local);
    }
    void save(false);
  }

  const input = (key: keyof Draft, label: string, extra: Record<string, unknown> = {}) => (
    <div className="field">
      <label htmlFor={fieldId(key)}>{label}</label>
      <input id={fieldId(key)} value={draft[key]} autoComplete="off" onChange={(e) => set(key, e.target.value)} {...described(key)} {...extra} />
      {err(key)}
    </div>
  );

  return (
    <form onSubmit={submit} noValidate aria-label="Add lead" className="form-grid activity-form">
      {failure && <p id={fieldId("message")} tabIndex={-1} className="form-error" role="alert">{failure}</p>}
      {input("name", "Student name (required)", { maxLength: 160 })}
      {input("email", "Email (required)", { type: "email", maxLength: 255, inputMode: "email" })}
      {input("phone", "Phone", { type: "tel", maxLength: 40 })}
      {input("interest", "Interest (required)", { maxLength: 180 })}
      <div className="field">
        <label htmlFor={fieldId("note")}>Note</label>
        <textarea id={fieldId("note")} value={draft.note} maxLength={NOTE_MAX} rows={3} onChange={(e) => set("note", e.target.value)}
          {...described("note", `${fieldId("note")}-hint`)} />
        <p id={`${fieldId("note")}-hint`} className="field-hint">Everyone who can see this organization can read this lead.</p>
        {err("note")}
      </div>
      {duplicate && (
        <BdmConfirm label="Possible duplicate" className="action-card" confirmText="Save anyway" busyText="Saving…" cancelText="Go back" busy={busy}
          onConfirm={() => void save(true)} onCancel={() => { setDuplicate(null); focus(fieldId("email")); }}>
          {duplicate.message}:{" "}
          {duplicate.matches.map((m) => `${m.name} (added ${formatDate(m.created_at)})`).join(", ")}
          {duplicate.total > duplicate.matches.length ? ` and ${duplicate.total - duplicate.matches.length} more` : ""}.
        </BdmConfirm>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !!duplicate}>{busy ? "Saving…" : "Save lead"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
