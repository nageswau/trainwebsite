"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import InterviewTemplateSelect from "@/components/InterviewTemplateSelect";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { AUTOMATION_URL, type AutomationSettings } from "@/lib/recruiterInterviews";

type HourKey = "first_reminder_hours" | "second_reminder_hours" | "chase_after_hours" | "escalate_after_hours";
const HOURS: { key: HourKey; label: string; max: number; hint: string }[] = [
  { key: "first_reminder_hours", label: "First reminder (hours before)", max: 168, hint: "Blank switches it off. Default 24." },
  { key: "second_reminder_hours", label: "Second reminder (hours before)", max: 168, hint: "Sooner than the first. Default 2." },
  { key: "chase_after_hours", label: "Chase client feedback after (hours)", max: 720, hint: "After the interview ends, a follow-up is created. Default 24." },
  { key: "escalate_after_hours", label: "Escalate to Team Lead after (hours)", max: 720, hint: "If the follow-up is still open. Default 24." },
];
type Form = Record<HourKey, string> & { reminder_template_id: string; chase_template_id: string };
const toForm = (s: AutomationSettings): Form => ({
  ...(Object.fromEntries(HOURS.map(({ key }) => [key, s[key] === null ? "" : String(s[key])])) as Record<HourKey, string>),
  reminder_template_id: s.reminder_template_id ?? "", chase_template_id: s.chase_template_id ?? "",
});

/** pob-022 (DEC-SCOPE-421 A2/A9): the Team Lead's interview automation -- the reminder slots, the feedback chase and its escalation, and the
 * approved templates they use. One form, saved as a whole; the API checks every rule and its 422s land on their fields. */
export default function InterviewAutomationSettings() {
  const id = useId();
  const [form, setForm] = useState<Form | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(AUTOMATION_URL, { signal: controller.signal })
      .then(async (r) => (r.ok ? setForm(toForm(await r.json())) : setLoadFailed(true)))
      .catch(() => !controller.signal.aborted && setLoadFailed(true));
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form || inFlight.current) return;
    const invalid = HOURS.filter(({ key, max }) => form[key] !== "" && !(/^\d+$/.test(form[key]) && Number(form[key]) >= 1 && Number(form[key]) <= max));
    if (invalid.length) return setErrors(Object.fromEntries(invalid.map(({ key, max }) => [key, `Enter whole hours from 1 to ${max}, or leave it blank`])));
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setMessage(null);
    const body = { ...Object.fromEntries(HOURS.map(({ key }) => [key, form[key] === "" ? null : Number(form[key])])),
      reminder_template_id: form.reminder_template_id || null, chase_template_id: form.chase_template_id || null };
    const result = await sendJson(AUTOMATION_URL, "PUT", body);
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      setForm(toForm(result.data as AutomationSettings));
      return setMessage({ ok: true, text: "Interview automation saved." });
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    setMessage({ ok: false, text: writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message });
  }

  const set = (key: keyof Form) => (value: string) => form && setForm({ ...form, [key]: value });
  return (
    <section className="action-card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ marginTop: 0 }}>Interview automation</h3>
      <p className="muted" style={{ marginTop: 0 }}>Reminders before each interview, and a follow-up when client feedback is late.</p>
      {loadFailed && <p className="form-error" role="alert">The automation settings could not be loaded. Refresh the page to try again.</p>}
      {!form && !loadFailed && <p className="muted" role="status">Loading automation settings…</p>}
      {form && (
        <form noValidate onSubmit={submit} aria-label="Interview automation">
          <div className="form-grid" style={{ display: "grid", gap: 8, alignItems: "start", gridTemplateColumns: "repeat(auto-fit, minmax(min(15rem, 100%), 1fr))" }}>
            {HOURS.map(({ key, label, max, hint }) => (
              <div className="field" key={key}>
                <label htmlFor={`${id}-${key}`}>{label}</label>
                <input id={`${id}-${key}`} type="number" inputMode="numeric" min={1} max={max} step={1} value={form[key]} onChange={(e) => set(key)(e.target.value)}
                  aria-invalid={errors[key] ? true : undefined} aria-describedby={`${id}-${key}-hint${errors[key] ? ` ${id}-${key}-error` : ""}`} />
                <p id={`${id}-${key}-hint`} className="muted" style={{ margin: 0, fontSize: 13 }}>{hint}</p>
                {errors[key] && <p id={`${id}-${key}-error`} className="form-error">{errors[key]}</p>}
              </div>
            ))}
            <InterviewTemplateSelect id={`${id}-reminder`} label="Reminder message" value={form.reminder_template_id} onChange={set("reminder_template_id")}
              error={errors.reminder_template_id} />
            <InterviewTemplateSelect id={`${id}-chase`} label="Feedback chase message" value={form.chase_template_id} onChange={set("chase_template_id")}
              error={errors.chase_template_id} />
          </div>
          {message && <p className={message.ok ? "muted" : "form-error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save automation"}</button>
          </div>
        </form>
      )}
    </section>
  );
}
