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
          branch: form.get("branch") || undefined,
          address: form.get("address") || undefined,
          contact_number: form.get("contact_number") || undefined,
          email: form.get("email") || undefined,
          website: form.get("website") || undefined,
          grades_available: form.get("grades_available") || undefined,
          board: form.get("board") || undefined,
          partnership_date: form.get("partnership_date") || undefined,
          mou_reference: form.get("mou_reference") || undefined,
          edusphere_bdm: form.get("edusphere_bdm") || undefined,
          monthly_visit_schedule: form.get("monthly_visit_schedule") || undefined,
          vice_principal_name: form.get("vice_principal_name") || undefined,
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
    setMessage(welcomeLinkFeedback(`School created. School code ${data.school_code}. Coordinator account ready for ${data.coordinator_email}.`, data));
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Create school</h3>
      <form className="form" onSubmit={submit}>
        <fieldset className="question">
          <legend>Identity</legend>
          <div className="field"><label htmlFor="school-name">School name</label><input id="school-name" name="name" required /></div>
          <div className="field"><label htmlFor="school-branch">Branch</label><input id="school-branch" name="branch" /></div>
          <div className="field"><label htmlFor="school-address">Address</label><input id="school-address" name="address" /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-city">City</label><input id="school-city" name="city" /></div>
            <div className="field"><label htmlFor="school-state">State</label><input id="school-state" name="state" /></div>
          </div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-contact-number">Contact number</label><input id="school-contact-number" name="contact_number" /></div>
            <div className="field"><label htmlFor="school-email">Email</label><input id="school-email" name="email" type="email" /></div>
          </div>
          <div className="field"><label htmlFor="school-website">Website</label><input id="school-website" name="website" /></div>
        </fieldset>
        <fieldset className="question">
          <legend>Academic</legend>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-grades">Grades available</label><input id="school-grades" name="grades_available" /></div>
            <div className="field">
              <label htmlFor="school-board">Board</label>
              <select id="school-board" name="board" defaultValue="">
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
        </fieldset>
        <fieldset className="question">
          <legend>Partnership</legend>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="school-tier">Partnership tier</label>
              <select id="school-tier" name="tier" defaultValue="">
                <option value="">Not set</option>
                <option value="bronze">Bronze</option>
                <option value="silver">Silver</option>
                <option value="gold">Gold</option>
                <option value="platinum">Platinum</option>
              </select>
            </div>
            <div className="field"><label htmlFor="school-partnership-date">Partnership date</label><input id="school-partnership-date" name="partnership_date" type="date" /></div>
          </div>
          <div className="field"><label htmlFor="school-mou">Agreement / MoU reference</label><input id="school-mou" name="mou_reference" /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-bdm">Edusphere BDM</label><input id="school-bdm" name="edusphere_bdm" /></div>
            <div className="field"><label htmlFor="school-vp">Vice Principal</label><input id="school-vp" name="vice_principal_name" /></div>
          </div>
          <div className="field"><label htmlFor="school-visits">Monthly visit schedule</label><input id="school-visits" name="monthly_visit_schedule" /></div>
        </fieldset>
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
