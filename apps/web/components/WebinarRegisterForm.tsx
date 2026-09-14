"use client";
import { FormEvent, useState } from "react";

export default function WebinarRegisterForm({ eventId, label = "webinar" }: { eventId: string; label?: string }) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    // Capture the form element before the await -- the DOM nulls e.currentTarget once
    // event dispatch finishes, so using it after `await fetch` can throw intermittently.
    const formElement = e.currentTarget;
    setLoading(true);
    setMessage("");
    const f = new FormData(formElement);
    const payload = { full_name: f.get("full_name"), email: f.get("email"), phone: f.get("phone") };
    const r = await fetch(`/api/v1/public/webinars/${eventId}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setLoading(false);
    setMessage(r.ok ? "Registration confirmed. We'll email you the joining details before the session." : "We could not complete your registration. Please review the fields and try again.");
    if (r.ok) formElement.reset();
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="webinar-register-name">Full name *</label>
          <input id="webinar-register-name" name="full_name" required />
        </div>
        <div className="field">
          <label htmlFor="webinar-register-email">Email *</label>
          <input id="webinar-register-email" name="email" type="email" required />
        </div>
      </div>
      <div className="field">
        <label htmlFor="webinar-register-phone">Phone</label>
        <input id="webinar-register-phone" name="phone" type="tel" />
      </div>
      <button className="btn" disabled={loading}>{loading ? "Registering…" : `Register for this ${label}`}</button>
      {message && (
        <div className={message.startsWith("Registration confirmed") ? "form-message" : "form-error"} role="status" aria-live="polite">
          {message}
        </div>
      )}
    </form>
  );
}
