"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { sendJson } from "@/lib/apiErrors";

type Counselor = { id: string; name: string; division: string; active: boolean };

// One list per page load, shared by every row's picker; a failed load is dropped so the next open retries it.
let counselorList: Promise<Counselor[]> | null = null;

function loadCounselors() {
  if (!counselorList) {
    const request: Promise<Counselor[]> = fetch("/api/v1/admin/users?role=counselor")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("load failed"))))
      .then((users: Counselor[]) => {
        if (!Array.isArray(users)) throw new Error("bad list");
        return users.filter((u) => u.active && u.division === "overseas");
      })
      .catch((error) => {
        if (counselorList === request) counselorList = null;
        throw error;
      });
    counselorList = request;
  }
  return counselorList;
}

export function clearCounselorListCache() {
  counselorList = null;
}

// AGN-023 (DEC-SCOPE-090 §3.1, §6): the Overseas Admin assigns or swaps an application's EduSphere counselor. Swap only (H8): there
// is no "none" choice. The picker lists active overseas counselors; the server re-checks every rule.
export default function AssignCounselorButton({ applicationId, currentId }: { applicationId: string; currentId: string | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [counselors, setCounselors] = useState<Counselor[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const label = currentId ? "Change counsellor" : "Assign counsellor";
  const buttonRef = useRef<HTMLButtonElement>(null);
  const selectRef = useRef<HTMLSelectElement>(null);
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const requestId = useRef(0);
  const refocusButton = useRef(false);
  const selectId = `assign-counselor-${applicationId}`;

  // Focus follows the picker: the select (or the load-failed / empty message) once it renders, the button once the form closes.
  useEffect(() => {
    if (open) (selectRef.current ?? noticeRef.current)?.focus();
    else if (refocusButton.current) {
      refocusButton.current = false;
      buttonRef.current?.focus();
    }
  }, [open, counselors, loadFailed]);

  useEffect(() => () => { requestId.current += 1; }, []);

  function close() {
    requestId.current += 1; // ignore a load still in flight for this form
    refocusButton.current = true;
    setOpen(false);
  }

  function start() {
    const mine = ++requestId.current;
    setOpen(true);
    setMessage(null);
    setLoadFailed(false);
    setCounselors(null);
    loadCounselors()
      .then((list) => { if (mine === requestId.current) setCounselors(list); })
      .catch(() => { if (mine === requestId.current) setLoadFailed(true); });
  }

  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape" && !busy) close();
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const counselorId = String(new FormData(event.currentTarget).get("counselor_id") || "");
    if (!counselorId) return;
    setBusy(true);
    const result = await sendJson(`/api/v1/workflows/overseas/applications/${applicationId}/counselor`, "PUT", { counselor_id: counselorId });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
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
        <form className="form" onSubmit={save} onKeyDown={onKeyDown} aria-label={label}>
          <div className="field">
            <label htmlFor={selectId}>EduSphere counsellor</label>
            {loadFailed ? (
              <p className="form-error" role="alert" ref={noticeRef} tabIndex={-1}>Couldn&apos;t load the counsellors -- try again.</p>
            ) : counselors === null ? (
              <p className="muted">Loading counsellors…</p>
            ) : counselors.length === 0 ? (
              <p className="muted" ref={noticeRef} tabIndex={-1}>No active overseas counsellors.</p>
            ) : (
              <select id={selectId} ref={selectRef} name="counselor_id" defaultValue={currentId ?? ""} required>
                <option value="" disabled>Choose…</option>
                {counselors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
          <button className="btn small" disabled={busy || loadFailed || !counselors?.length}>{busy ? "Saving…" : "Save"}</button>{" "}
          <button type="button" className="btn small secondary" onClick={close}>Cancel</button>
        </form>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
    </div>
  );
}
