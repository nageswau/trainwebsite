"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { type Feedback, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to create school.";
}

// SCH-003 (DEC-SCOPE-012): Overseas Admin creates the School partner record and its seed
// Coordinator account in one step -- both active immediately, no approval gate. Same
// "dedicated create panel next to the generic read-only portal section" split already
// established for AdminUniversityCreatePanel (RAID.md I-32).
export default function AdminSchoolCreatePanel() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Feedback | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    let response: Response;
    try {
      response = await fetch("/api/v1/overseas-admin/schools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          city: form.get("city") || undefined,
          state: form.get("state") || undefined,
          coordinator_full_name: form.get("coordinator_full_name"),
          coordinator_email: form.get("coordinator_email"),
          tier: form.get("tier") || undefined,
        }),
      });
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- it is not known whether the school was created. Check the schools list before trying again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    setMessage(welcomeLinkFeedback(`School created. Coordinator account ready for ${data.coordinator_email}.`, data));
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Create school</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="school-name">School name</label>
          <input id="school-name" name="name" required />
        </div>
        <div className="field">
          <label htmlFor="school-city">City</label>
          <input id="school-city" name="city" />
        </div>
        <div className="field">
          <label htmlFor="school-state">State</label>
          <input id="school-state" name="state" />
        </div>
        <div className="field">
          <label htmlFor="school-tier">Partnership tier</label>
          <select id="school-tier" name="tier" defaultValue="">
            <option value="">Not set yet</option>
            <option value="bronze">Bronze</option>
            <option value="silver">Silver</option>
            <option value="gold">Gold</option>
            <option value="platinum">Platinum</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="school-coordinator-name">Coordinator full name</label>
          <input id="school-coordinator-name" name="coordinator_full_name" required />
        </div>
        <div className="field">
          <label htmlFor="school-coordinator-email">Coordinator email</label>
          <input id="school-coordinator-email" name="coordinator_email" type="email" required />
        </div>
        <button className="btn" disabled={busy}>
          {busy ? "Creating…" : "Create school + seed Coordinator"}
        </button>
      </form>
      {message && (
        <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
