"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { acceptConsentUrl, type MyConsent } from "@/lib/overseasConsents";

/** ccrm-040 (DEC-SCOPE-276 CN2/CN3): the overseas student's consent request, leading the dashboard until every current consent is
 *  given. Not blocking: the rest of the portal works. Each consent is its own checkbox (the student may give one and not the other);
 *  "Save" records the ticked ones and the page re-reads. Communication channels stay on the existing preferences page (ENH-014). */
export default function OverseasConsentCard({ items }: { items: MyConsent[] }) {
  const router = useRouter();
  const pending = items.filter((i) => !i.accepted_at);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (pending.length === 0) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (ticked.size === 0) return setError("Tick at least one consent to save.");
    setBusy(true);
    setError(null);
    for (const id of ticked) {
      const result = await sendJson(acceptConsentUrl(id), "POST", {});
      if (!result.ok) {
        setBusy(false);
        setError(result.message);
        router.refresh();
        return;
      }
    }
    setBusy(false);
    setTicked(new Set());
    router.refresh();
  }

  function toggle(id: string, on: boolean) {
    setTicked((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  return (
    <form className="card" aria-labelledby="consent-heading" onSubmit={submit} noValidate>
      <h2 id="consent-heading">Your consent</h2>
      <p className="muted">Before we work on your applications, please read and agree to how we use and share your information.</p>
      {pending.map((item) => (
        <fieldset key={item.id} style={{ border: 0, padding: 0, margin: "12px 0" }}>
          <legend><strong>{item.title}</strong> <span className="muted">({item.version})</span></legend>
          <p style={{ margin: "4px 0 8px" }}>{item.body}</p>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={ticked.has(item.id)} disabled={busy} onChange={(e) => toggle(item.id, e.target.checked)} />
            I agree
          </label>
        </fieldset>
      ))}
      <p className="muted" style={{ fontSize: 13 }}>
        Choose how we may contact you (WhatsApp, SMS) on <Link href="/account/profile">your notification preferences</Link>.
      </p>
      <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save consent"}</button>
      {error && <p className="form-error" role="alert" style={{ margin: "8px 0 0" }}>{error}</p>}
    </form>
  );
}
