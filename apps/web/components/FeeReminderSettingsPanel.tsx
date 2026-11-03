"use client";

import { type FormEvent, useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";

// itc-016 (DEC-SCOPE-358 F3): the IT Admin's fee-reminder schedule. The daily 08:30 IST job reminds the student the given days before a
// due date and on each given day after it (the linked counselor hears of overdue ones too). 0 / blank switches a rule off.
export const FEE_REMINDER_SETTINGS_URL = "/api/v1/admin/it/fee-reminder-settings";
type Schedule = { days_before: number; overdue_days: number[] };

const BEFORE_HINT = "Enter a whole number of days from 0 to 30.";
const AFTER_HINT = "Enter up to 6 whole numbers from 1 to 90, separated by commas.";

/** "1, 7, 14" -> [1, 7, 14] (distinct, sorted); null when any entry is not a whole number from 1 to 90 or there are more than 6. */
function parseDays(text: string): number[] | null {
  const parts = text.split(",").map((p) => p.trim()).filter(Boolean);
  if (!parts.every((p) => /^\d+$/.test(p))) return null;
  const days = [...new Set(parts.map(Number))].sort((a, b) => a - b);
  return days.length <= 6 && days.every((d) => d >= 1 && d <= 90) ? days : null;
}

/** [1] -> "1 day", [1, 7, 14] -> "1, 7 and 14 days" (QA16-01). */
function dayList(days: number[]) {
  const list = days.length > 1 ? `${days.slice(0, -1).join(", ")} and ${days[days.length - 1]}` : String(days[0]);
  return `${list} day${days.length === 1 && days[0] === 1 ? "" : "s"}`;
}

function summary(s: Schedule) {
  const rules = [s.days_before ? `${dayList([s.days_before])} before the due date` : null, s.overdue_days.length ? `${dayList(s.overdue_days)} after it` : null].filter(Boolean);
  return rules.length ? `Now: ${rules.join(" and ")}.` : "Reminders are off.";
}

export default function FeeReminderSettingsPanel() {
  const [saved, setSaved] = useState<Schedule | null>(null);
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);

  function show(s: Schedule) {
    setSaved(s);
    setBefore(String(s.days_before));
    setAfter(s.overdue_days.join(", "));
  }

  useEffect(() => {
    fetch(FEE_REMINDER_SETTINGS_URL, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        const data = await r.json();
        if (typeof data?.days_before !== "number" || !Array.isArray(data?.overdue_days)) throw new Error("shape");
        show(data);
      })
      .catch(() => setLoadError(true));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!saved || busy) return;
    const daysBefore = Number(before);
    if (!/^\d+$/.test(before.trim()) || daysBefore > 30) return setNotice({ text: BEFORE_HINT, failed: true });
    const overdueDays = parseDays(after);
    if (overdueDays === null) return setNotice({ text: AFTER_HINT, failed: true });
    setBusy(true);
    setNotice(null);
    const outcome = await sendJson(FEE_REMINDER_SETTINGS_URL, "PUT", { days_before: daysBefore, overdue_days: overdueDays });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    show(outcome.data as Schedule);
    setNotice({ text: "Reminder schedule saved. It applies from the next daily run.", failed: false });
  }

  return (
    <section aria-labelledby="fee-reminders-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="fee-reminders-heading" style={{ margin: 0 }}>Fee reminders</h3>
      <p className="muted" style={{ margin: 0 }}>
        Each morning students are reminded of an IT course fee before it is due and on the chosen days after it is overdue; their counselor hears
        of overdue fees too. Reminders never show an amount.
      </p>
      {loadError ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>The reminder schedule could not be loaded. Refresh the page to try again.</p>
      ) : !saved ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading…</p>
      ) : (
        <form onSubmit={save} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="fee-reminder-before">Days before the due date</label>
            <input id="fee-reminder-before" type="number" inputMode="numeric" min={0} max={30} step={1} value={before}
              onChange={(e) => setBefore(e.target.value)} disabled={busy} aria-describedby="fee-reminder-before-hint" style={{ width: "8rem" }} />
            <span id="fee-reminder-before-hint" className="muted" style={{ fontSize: 13 }}>0–30 · 0 = off</span>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="fee-reminder-after">Days after the due date</label>
            <input id="fee-reminder-after" type="text" inputMode="numeric" value={after} onChange={(e) => setAfter(e.target.value)} disabled={busy}
              aria-describedby="fee-reminder-after-hint" placeholder="1, 7, 14" style={{ width: "10rem" }} />
            <span id="fee-reminder-after-hint" className="muted" style={{ fontSize: 13 }}>Up to 6, from 1 to 90 · blank = off</span>
          </div>
          <button type="submit" className="btn secondary small" disabled={busy} aria-busy={busy}>{busy ? "Saving…" : "Update reminder schedule"}</button>
        </form>
      )}
      {saved && <p className="muted" style={{ margin: 0, fontSize: 13 }}>{summary(saved)}</p>}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
    </section>
  );
}
