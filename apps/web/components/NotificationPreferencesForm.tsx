"use client";

import { type CSSProperties, type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { isNotificationPreferences, type NotificationPreferences } from "@/lib/types";

// ENH-014 (spec §7): WhatsApp/SMS opt-in. Consent is deliberate, so toggles never autosave -- the user presses Save.
// Same patterns as ProfileForm: a ref guards double submits, "Saving…" is announced but visually hidden, focus returns
// to the button after a save. Server-side validation is the source of truth (a 422 message is shown as-is).
const VISUALLY_HIDDEN: CSSProperties = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };
const NEXT = encodeURIComponent("/account/profile");
const HINT_ID = "notification-phone-hint";
const SAVE_FAILED = "Couldn't save your settings. Check your connection and try again.";

type Channel = "whatsapp" | "sms";
type Choice = Record<Channel, boolean>;

export default function NotificationPreferencesForm({ initial, phone }: { initial: NotificationPreferences; phone: string | null }) {
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState<Choice>({ whatsapp: initial.whatsapp, sms: initial.sms });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [focusTick, setFocusTick] = useState(0);
  const submitting = useRef(false);
  const saveButton = useRef<HTMLButtonElement>(null);

  // A phone saved in ProfileForm triggers router.refresh(); the server sends new props (phone_valid may change).
  useEffect(() => {
    setSaved(initial);
    setDraft({ whatsapp: initial.whatsapp, sms: initial.sms });
  }, [initial.whatsapp, initial.sms, initial.phone_valid]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (focusTick) saveButton.current?.focus();
  }, [focusTick]);

  function finish(next: FormMessageState | null) {
    setMessage(next);
    submitting.current = false;
    setBusy(false);
    setFocusTick((t) => t + 1);
  }

  function revert(text: string) {
    setDraft({ whatsapp: saved.whatsapp, sms: saved.sms });
    finish({ text, failed: true });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setMessage(null);
    setSignedOut(false);
    let response: Response;
    try {
      response = await fetch("/api/v1/account/notification-preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
    } catch {
      revert(SAVE_FAILED);
      return;
    }
    const body: unknown = await response.json().catch(() => null);
    if (response.ok && isNotificationPreferences(body)) {
      setSaved(body);
      setDraft({ whatsapp: body.whatsapp, sms: body.sms });
      finish({ text: "Notification settings saved.", failed: false });
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      setDraft({ whatsapp: saved.whatsapp, sms: saved.sms });
      finish(null);
      return;
    }
    const detail = (body as { detail?: unknown } | null)?.detail;
    revert(response.status === 422 && typeof detail === "string" ? detail : SAVE_FAILED);
  }

  const canTurnOn = saved.phone_valid;
  const channels: { key: Channel; label: string; detail: string }[] = [
    { key: "whatsapp", label: "WhatsApp", detail: phone ? `Messages go to ${phone}` : "" },
    { key: "sms", label: "SMS", detail: phone ? `Texts go to ${phone}` : "" },
  ];

  return (
    <form className="form" onSubmit={submit} aria-label="Notification settings" aria-busy={busy} noValidate>
      <fieldset className="form-section">
        <legend>Send me updates by</legend>
        {[
          { id: "notify-email", label: "Email" },
          { id: "notify-in-app", label: "In-app" },
        ].map((row) => (
          <label key={row.id} className="pf-check" htmlFor={row.id}>
            <input id={row.id} type="checkbox" checked disabled readOnly aria-describedby={`${row.id}-hint`} />
            <span>
              {row.label} <span id={`${row.id}-hint`} className="field-hint">Always on</span>
            </span>
          </label>
        ))}
        {channels.map(({ key, label, detail }) => {
          const locked = !canTurnOn && !draft[key];
          return (
            <label key={key} className="pf-check" htmlFor={`notify-${key}`}>
              <input
                id={`notify-${key}`}
                type="checkbox"
                checked={draft[key]}
                disabled={locked}
                aria-describedby={canTurnOn ? undefined : HINT_ID}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.checked }))}
              />
              <span>
                {label} {detail && <span className="field-hint">{detail}</span>}
              </span>
            </label>
          );
        })}
        {!canTurnOn && (
          <p id={HINT_ID} className="field-hint">
            <a href="#profile-phone">Add a mobile number</a> in your profile above to turn on WhatsApp or SMS.
          </p>
        )}
        <p className="field-hint">By turning on WhatsApp or SMS you agree to receive these messages from EduSphere. You can turn them off here at any time.</p>
      </fieldset>
      {message && <FormMessage message={message} />}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to change your notification settings.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {busy && (
        <div role="status" aria-live="polite" style={VISUALLY_HIDDEN}>
          Saving your notification settings…
        </div>
      )}
      <button ref={saveButton} className="btn" aria-disabled={busy}>
        {busy ? "Saving…" : "Save notification settings"}
      </button>
    </form>
  );
}
