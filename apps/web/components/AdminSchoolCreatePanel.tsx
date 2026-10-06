"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { gradesText, type OnboardingItem } from "@/lib/bdmOnboarding";
import { type Feedback, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

type Prefill = Partial<Record<"name" | "branch" | "address" | "city" | "state" | "contact_number" | "email" | "website" | "grades_available" | "board"
  | "partnership_date" | "mou_reference" | "vice_principal_name" | "monthly_visit_schedule" | "coordinator_full_name" | "coordinator_email", string>>;

// bdm-018: the organization's details as the School's (read live by the queue); the coordinator suggestion is the primary contact.
function prefillOf({ organization: o, mou, primary_contact: contact }: OnboardingItem): Prefill {
  return {
    name: o.name, city: o.city, state: o.state ?? "", address: o.address ?? "", contact_number: o.phone ?? "", email: o.email ?? "", website: o.website ?? "",
    board: o.board ?? "", grades_available: gradesText(o.grade_from, o.grade_to), mou_reference: mou?.reference ?? "", partnership_date: mou?.signed_on ?? "",
    coordinator_full_name: contact?.name ?? "", coordinator_email: contact?.email ?? "",
  };
}

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to create school.";
}

// SCH-003 (DEC-SCOPE-012): Overseas Admin creates the School partner record and its seed
// Coordinator account in one step -- both active immediately, no approval gate. Same
// "dedicated create panel next to the generic read-only portal section" split already
// established for AdminUniversityCreatePanel (RAID.md I-32).
// bdm-018 (spec §6): with a BDM onboarding `request`, the form is prefilled from the organization (the admin checks and edits it) and
// the create sends `bdm_onboarding_request_id`, so the School is linked to the organization in the same transaction.
export default function AdminSchoolCreatePanel({ request = null, onClear, onCreated }: { request?: OnboardingItem | null; onClear?: () => void; onCreated?: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Feedback | null>(null);
  const prefill: Prefill = request ? prefillOf(request) : {};

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
          monthly_visit_schedule: form.get("monthly_visit_schedule") || undefined,
          vice_principal_name: form.get("vice_principal_name") || undefined,
          bdm_onboarding_request_id: request?.id,
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
    const linked = request ? ` Linked to ${request.organization.code}; the BDM has been told.` : "";
    setMessage(welcomeLinkFeedback(`School created. School code ${data.school_code}. Coordinator account ready for ${data.coordinator_email}.${linked}`, data));
    formElement.reset();
    onCreated?.();
    router.refresh();
  }

  const value = (name: keyof Prefill) => prefill[name] ?? "";
  return (
    <div className="action-card">
      <h3>Create school</h3>
      {request && (
        <div className="form-message" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
          <span>Creating the School for {request.organization.code} · {request.organization.name} (requested by {request.requested_by.full_name}). Check the details before creating.</span>
          <button type="button" className="btn secondary small" onClick={onClear} disabled={busy}>Clear</button>
        </div>
      )}
      {/* bdm-018: a new request remounts the form, so its defaults are the request's (uncontrolled inputs, as before) */}
      <form key={request?.id ?? "blank"} className="form" onSubmit={submit}>
        <fieldset className="question">
          <legend>Identity</legend>
          <div className="field"><label htmlFor="school-name">School name</label><input id="school-name" name="name" defaultValue={value("name")} required /></div>
          <div className="field"><label htmlFor="school-branch">Branch</label><input id="school-branch" name="branch" defaultValue={value("branch")} /></div>
          <div className="field"><label htmlFor="school-address">Address</label><input id="school-address" name="address" defaultValue={value("address")} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-city">City</label><input id="school-city" name="city" defaultValue={value("city")} /></div>
            <div className="field"><label htmlFor="school-state">State</label><input id="school-state" name="state" defaultValue={value("state")} /></div>
          </div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-contact-number">Contact number</label><input id="school-contact-number" name="contact_number" defaultValue={value("contact_number")} /></div>
            <div className="field"><label htmlFor="school-email">Email</label><input id="school-email" name="email" defaultValue={value("email")} type="email" /></div>
          </div>
          <div className="field"><label htmlFor="school-website">Website</label><input id="school-website" name="website" defaultValue={value("website")} /></div>
        </fieldset>
        <fieldset className="question">
          <legend>Academic</legend>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-grades">Grades available</label><input id="school-grades" name="grades_available" defaultValue={value("grades_available")} /></div>
            <div className="field">
              <label htmlFor="school-board">Board</label>
              <select id="school-board" name="board" defaultValue={value("board")}>
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
            <div className="field"><label htmlFor="school-partnership-date">Partnership date</label><input id="school-partnership-date" name="partnership_date" defaultValue={value("partnership_date")} type="date" /></div>
          </div>
          <div className="field"><label htmlFor="school-mou">Agreement / MoU reference</label><input id="school-mou" name="mou_reference" defaultValue={value("mou_reference")} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-vp">Vice Principal</label><input id="school-vp" name="vice_principal_name" defaultValue={value("vice_principal_name")} /></div>
          </div>
          <div className="field"><label htmlFor="school-visits">Monthly visit schedule</label><input id="school-visits" name="monthly_visit_schedule" defaultValue={value("monthly_visit_schedule")} /></div>
        </fieldset>
        <div className="field">
          <label htmlFor="school-coordinator-name">Coordinator full name</label>
          <input id="school-coordinator-name" name="coordinator_full_name" defaultValue={value("coordinator_full_name")} required />
        </div>
        <div className="field">
          <label htmlFor="school-coordinator-email">Coordinator email</label>
          <input id="school-coordinator-email" name="coordinator_email" defaultValue={value("coordinator_email")} type="email" required />
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
