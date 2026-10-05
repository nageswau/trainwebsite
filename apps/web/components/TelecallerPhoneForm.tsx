"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { PROFILE_URL } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const MESSAGE_ID = "telecaller-phone-message";

// tel-001 (TL3): the one field a telecaller edits about themselves. A failed save keeps what was typed and moves focus to the
// server's message; success is announced and the server-rendered card refreshes.
export default function TelecallerPhoneForm({ phone }: { phone: string | null }) {
  const router = useRouter();
  const [value, setValue] = useState(phone ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const focus = useFocusAfterRender();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const outcome = await sendJson(PROFILE_URL, "PATCH", { phone: value.trim() || null });
    setBusy(false);
    if (outcome.ok) {
      setMessage({ text: "Mobile saved.", error: false });
      router.refresh();
    } else {
      setMessage({ text: outcome.message, error: true });
      focus(MESSAGE_ID);
    }
  }

  return (
    <form className="card form" style={{ padding: 16, marginTop: 16 }} onSubmit={submit} aria-describedby={MESSAGE_ID}>
      <div className="field">
        <label htmlFor="telecaller-phone">Mobile</label>
        <input id="telecaller-phone" name="phone" type="tel" inputMode="tel" maxLength={40} value={value} onChange={(e) => setValue(e.target.value)} disabled={busy} />
      </div>
      <button className="btn small" disabled={busy} aria-label="Save mobile">{busy ? "Saving…" : "Save mobile"}</button>
      <div id={MESSAGE_ID} tabIndex={-1} className={message ? (message.error ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={{ marginTop: 8 }}>
        {message?.text}
      </div>
    </form>
  );
}
