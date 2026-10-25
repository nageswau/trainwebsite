"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { lookupSearch, type PickOption } from "@/lib/lookups";

// AGN-023 (DEC-SCOPE-090 §3.1, §6): the Overseas Admin assigns or swaps an application's EduSphere counselor. Swap only (H8): there
// is no "none" choice. The picker is a type-ahead over the active overseas counselors (lookups/overseas-counselors, so the 500-row
// /admin/users cap cannot hide anyone); the server re-checks every rule.
// csc-005 (DEC-SCOPE-230): `url` points the same picker at a student's counselor (PUT /admin/users/{id}/counselor); default: the application.
export default function AssignCounselorButton({ applicationId, currentId, url }: { applicationId: string; currentId: string | null; url?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const label = currentId ? "Change counsellor" : "Assign counsellor";
  // ccrm-033 (DEC-SCOPE-268 RR1): replacing a counsellor needs a reason; a first assignment may give one. The server re-checks.
  const reasonRequired = currentId !== null;
  const trimmed = reason.trim();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const search = useMemo(() => lookupSearch("overseas-counselors"), []);
  const refocusButton = useRef(false);
  const refocusField = useRef(false);
  const selectId = `assign-counselor-${applicationId}`;

  // Focus follows the picker: the search field once it renders, the button once the form closes.
  useEffect(() => {
    if (open) fieldRef.current?.querySelector<HTMLInputElement>("input[role=combobox]")?.focus();
    else if (refocusButton.current) {
      refocusButton.current = false;
      buttonRef.current?.focus();
    }
  }, [open]);

  // After a failed save the field is enabled again (the focused Save button was disabled while saving), so focus returns to the search.
  useEffect(() => {
    if (!busy && refocusField.current) {
      refocusField.current = false;
      fieldRef.current?.querySelector<HTMLInputElement>("input[role=combobox]")?.focus();
    }
  }, [busy]);

  function close() {
    refocusButton.current = true;
    setOpen(false);
  }

  function start() {
    setOpen(true);
    setMessage(null);
    setPicked(null);
    setReason("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape" && !busy && !event.defaultPrevented) close(); // an Escape the list already handled only closes the list
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!picked || (reasonRequired && !trimmed)) return;
    setBusy(true);
    const body = { counselor_id: picked.id, ...(trimmed ? { reason: trimmed } : {}) };
    const result = await sendJson(url ?? `/api/v1/workflows/overseas/applications/${applicationId}/counselor`, "PUT", body);
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
      refocusField.current = true;
      return;
    }
    setMessage({ text: `${String(result.data.counselor_name)} assigned.`, failed: false });
    close();
    router.refresh();
  }

  return (
    <div>
      {!open ? (
        <button type="button" ref={buttonRef} className="btn small secondary" onClick={start}>{label}</button>
      ) : (
        <form className="form" onSubmit={save} onKeyDown={onKeyDown} aria-label={label} style={{ minWidth: "min(18rem, 70vw)" }}>
          <div ref={fieldRef}>
            <SearchableSelect id={selectId} name="counselor_id" label="EduSphere counsellor" noun="counsellor" required search={search} disabled={busy} onChange={setPicked} />
          </div>
          <div className="field">
            <label htmlFor={`${selectId}-reason`}>{reasonRequired ? "Reason for the change" : "Reason (optional)"}</label>
            <textarea id={`${selectId}-reason`} name="reason" rows={2} maxLength={500} required={reasonRequired} disabled={busy} value={reason}
              style={{ minHeight: "4.5rem" }} onChange={(event) => setReason(event.target.value)} />
          </div>
          <button className="btn small" disabled={busy || !picked || (reasonRequired && !trimmed)}>{busy ? "Saving…" : "Save"}</button>{" "}
          <button type="button" className="btn small secondary" onClick={close}>Cancel</button>
        </form>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
    </div>
  );
}
