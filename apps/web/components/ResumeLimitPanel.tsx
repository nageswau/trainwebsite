"use client";

import { type FormEvent, useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { RESUME_SETTINGS_URL, type ResumeSettings } from "@/lib/studentResumes";

// itc-026 (DEC-SCOPE-350 R4): the IT Admin's resume size limit, in whole MB. It applies to the next upload; resumes already stored are
// kept whatever their size.
export default function ResumeLimitPanel() {
  const [settings, setSettings] = useState<ResumeSettings | null>(null);
  const [value, setValue] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    fetch(RESUME_SETTINGS_URL, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        const data: ResumeSettings = await r.json();
        setSettings(data);
        setValue(String(data.max_mb));
      })
      .catch(() => setLoadError(true));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!settings || busy) return;
    const mb = Number(value);
    if (!Number.isInteger(mb) || mb < settings.min_mb || mb > settings.max_mb_ceiling) {
      return setNotice({ text: `Enter a whole number from ${settings.min_mb} to ${settings.max_mb_ceiling}.`, failed: true });
    }
    setBusy(true);
    setNotice(null);
    const outcome = await sendJson(RESUME_SETTINGS_URL, "PUT", { max_mb: mb });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    setSettings(outcome.data as ResumeSettings);
    setNotice({ text: `Resume limit saved: ${mb} MB.`, failed: false });
  }

  return (
    <section aria-labelledby="resume-limit-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="resume-limit-heading" style={{ margin: 0 }}>Resume upload limit</h3>
      <p className="muted" style={{ margin: 0 }}>The largest resume a student, counselor or IT Admin can upload. Resumes already uploaded are kept.</p>
      {loadError ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>The resume limit could not be loaded. Refresh the page to try again.</p>
      ) : !settings ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading…</p>
      ) : (
        <form onSubmit={save} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="resume-limit-mb">Limit (MB)</label>
            <input id="resume-limit-mb" type="number" inputMode="numeric" min={settings.min_mb} max={settings.max_mb_ceiling} step={1} value={value}
              onChange={(e) => setValue(e.target.value)} disabled={busy} aria-describedby="resume-limit-hint" style={{ width: "8rem" }} />
            <span id="resume-limit-hint" className="muted" style={{ fontSize: 13 }}>{settings.min_mb}–{settings.max_mb_ceiling} MB · now {settings.max_mb} MB</span>
          </div>
          <button type="submit" className="btn secondary small" disabled={busy} aria-busy={busy}>{busy ? "Saving…" : "Set limit"}</button>
        </form>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
    </section>
  );
}
