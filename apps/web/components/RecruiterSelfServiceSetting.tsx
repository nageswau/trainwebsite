"use client";

import { useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { labelOf, SELF_SERVICE_SETTINGS_URL, type FieldKey, type SelfServiceSettings } from "@/lib/candidatePortal";

// hrc-022 (DEC-SCOPE-384 C7): which fields external candidates may edit in their portal -- shown only to who may change it (placement
// managers, super_admin; the hrc-012 setting card idiom). Saved explicitly; the checkboxes keep their state if the save fails.
export default function RecruiterSelfServiceSetting() {
  const [setting, setSetting] = useState<SelfServiceSettings | null>(null);
  const [chosen, setChosen] = useState<FieldKey[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(SELF_SERVICE_SETTINGS_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: SelfServiceSettings | null) => {
        if (!s) return;
        setSetting(s);
        setChosen(s.fields);
      })
      .catch(() => undefined); // a failed read leaves the card hidden; the list keeps working
    return () => controller.abort();
  }, []);

  if (!setting?.can_edit) return null;

  async function save() {
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(SELF_SERVICE_SETTINGS_URL, "PUT", { fields: chosen });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: (outcome.status ?? 0) >= 500 ? "We couldn't save the setting. Please try again." : outcome.message, failed: true });
    setSetting(outcome.data as SelfServiceSettings);
    setMessage({ text: "Candidates can now edit the chosen fields in their portal.", failed: false });
  }

  const toggle = (key: FieldKey, on: boolean) => setChosen((now) => (on ? [...now, key] : now.filter((k) => k !== key)));
  return (
    <details className="action-card" style={{ marginBottom: 16 }}>
      <summary style={{ cursor: "pointer" }}>
        <strong>Candidate self-service fields</strong>
        <span className="muted" style={{ display: "block", fontSize: 13 }}>What external candidates may change in their own portal ({setting.fields.length} of {setting.available.length}).</span>
      </summary>
      <fieldset style={{ border: 0, padding: 0, margin: "12px 0 0", display: "grid", gap: 6, gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))" }}>
        <legend className="sr-only">Fields candidates may edit</legend>
        {setting.available.map((key) => (
          <label key={key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={chosen.includes(key)} disabled={busy} onChange={(e) => toggle(key, e.target.checked)} />
            {labelOf(key)}
          </label>
        ))}
      </fieldset>
      <p className="muted" style={{ fontSize: 13, margin: "10px 0" }}>Email and mobile are never self-service: an email change is verified by link, a mobile change goes through a recruiter.</p>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: "0 0 8px" }}>{message.text}</p>}
      <button className="btn small" type="button" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save fields"}</button>
    </details>
  );
}
