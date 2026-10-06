"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { sendJson } from "@/lib/apiErrors";

type Counselor = { id: string; name: string; division: string; active: boolean };

// AGN-023 (DEC-SCOPE-090 §3.1, §6): the Overseas Admin assigns or swaps an application's EduSphere counselor. Swap only (H8): there
// is no "none" choice. The picker lists active overseas counselors; the server re-checks every rule.
export default function AssignCounselorButton({ applicationId, currentId }: { applicationId: string; currentId: string | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [counselors, setCounselors] = useState<Counselor[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const label = currentId ? "Change counsellor" : "Assign counsellor";
  const selectId = `assign-counselor-${applicationId}`;

  function start() {
    setOpen(true);
    setMessage(null);
    fetch("/api/v1/admin/users?role=counselor")
      .then((res) => (res.ok ? res.json() : []))
      .then((users: Counselor[]) => setCounselors(users.filter((u) => u.active && u.division === "overseas")))
      .catch(() => setCounselors([]));
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
    const name = counselors?.find((c) => c.id === counselorId)?.name ?? "Counsellor";
    setMessage({ text: `${name} assigned.`, failed: false });
    setOpen(false);
    router.refresh();
  }

  return (
    <div>
      {!open ? (
        <button type="button" className="btn small secondary" onClick={start}>{label}</button>
      ) : (
        <form className="form" onSubmit={save} aria-label={label}>
          <div className="field">
            <label htmlFor={selectId}>EduSphere counsellor</label>
            {counselors === null ? (
              <p className="muted">Loading counsellors…</p>
            ) : (
              <select id={selectId} name="counselor_id" defaultValue={currentId ?? ""} required>
                <option value="" disabled>Choose…</option>
                {counselors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
          <button className="btn small" disabled={busy || counselors === null}>{busy ? "Saving…" : "Save"}</button>{" "}
          <button type="button" className="btn small secondary" onClick={() => setOpen(false)}>Cancel</button>
        </form>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
    </div>
  );
}
