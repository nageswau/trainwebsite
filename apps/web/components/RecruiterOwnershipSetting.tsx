"use client";

import { useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { OWNERSHIP_SETTINGS_URL } from "@/lib/recruiterCandidates";

type Setting = { shared_ownership: boolean; can_edit: boolean };

// hrc-012 (DEC-SCOPE-382 O4): the shared-ownership switch above the candidate list -- only for who may change it (placement managers,
// super_admin); everyone else sees nothing. The box moves at once and goes back if the save fails (the mgmt-026 optimistic idiom).
export default function RecruiterOwnershipSetting() {
  const [setting, setSetting] = useState<Setting | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(OWNERSHIP_SETTINGS_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: Setting | null) => s && setSetting(s))
      .catch(() => undefined); // a failed read leaves the switch hidden; the list keeps working
    return () => controller.abort();
  }, []);

  if (!setting?.can_edit) return null;

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setSetting((s) => s && { ...s, shared_ownership: next });
    const outcome = await sendJson(OWNERSHIP_SETTINGS_URL, "PUT", { shared_ownership: next });
    setBusy(false);
    if (!outcome.ok) {
      setSetting((s) => s && { ...s, shared_ownership: !next });
      return setMessage({ text: (outcome.status ?? 0) >= 500 ? "We couldn't save the setting. Please try again." : outcome.message, failed: true });
    }
    setMessage({ text: next ? "Collaborators can now be added to candidates." : "New collaborators can no longer be added. Existing ones stay until removed.", failed: false });
  }

  return (
    <div className="action-card" style={{ marginBottom: 16 }}>
      <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <input type="checkbox" checked={setting.shared_ownership} disabled={busy} onChange={(e) => void toggle(e.target.checked)} style={{ marginTop: 4 }} />
        <span>
          <strong>Allow collaborators on candidates</strong>
          <span className="muted" style={{ display: "block", fontSize: 13 }}>
            When on, a candidate&apos;s primary recruiter can share them with other recruiters or placement officers. Each candidate always keeps one primary recruiter.
          </span>
        </span>
      </label>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: "8px 0 0" }}>{message.text}</p>}
    </div>
  );
}
