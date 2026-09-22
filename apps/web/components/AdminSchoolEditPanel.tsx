"use client";

import { FormEvent, useState } from "react";

import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import { type Feedback, toneClass } from "@/lib/welcomeLink";

type School = {
  id: string; school_code: string | null; name: string;
  branch: string | null; address: string | null; contact_number: string | null;
  email: string | null; website: string | null; grades_available: string | null;
  board: string | null; partnership_date: string | null; mou_reference: string | null;
  edusphere_bdm: string | null; monthly_visit_schedule: string | null; vice_principal_name: string | null;
};

// ENH-009 / DEC-SCOPE-023: lookup-by-code then PATCH, mirroring the existing
// GET .../school-students/lookup?code= convention (admin.py:1240) -- the codebase has no
// clickable-table-row-to-edit pattern anywhere, and the established convention is "read via the
// generic portal section, write via a dedicated panel" (same split as AdminSchoolCreatePanel.tsx).
export default function AdminSchoolEditPanel() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Feedback | null>(null);
  const [school, setSchool] = useState<School | null>(null);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    setBusy(true);
    setMessage(null);
    setSchool(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/lookup?code=${encodeURIComponent(String(code))}`);
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- check your connection and try again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail, "Unable to look up that school."), tone: "error" });
      return;
    }
    setSchool(data as School);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${school.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
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
      setMessage({ text: "Network error -- it is not known whether the changes saved. Look the school up again before retrying.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    if (!isRequestBody(data)) {
      setMessage({ text: "The save could not be confirmed. Look the school up again before changing anything else.", tone: "error" });
      return;
    }
    setSchool(data as School);
    setMessage({ text: "School profile updated.", tone: "success" });
  }

  return (
    <div className="action-card">
      <h3>Edit school profile</h3>
      <form className="form" onSubmit={lookup}>
        <div className="field">
          <label htmlFor="school-lookup-code">School ID</label>
          <input id="school-lookup-code" name="code" required />
        </div>
        <button className="btn" disabled={busy}>{busy ? "Looking up…" : "Look up"}</button>
      </form>
      {school && (
        <form className="form" onSubmit={save} style={{ marginTop: 16 }}>
          <p className="muted">{school.name} ({school.school_code})</p>
          <div className="field"><label htmlFor="edit-branch">Branch</label><input id="edit-branch" name="branch" defaultValue={school.branch ?? ""} /></div>
          <div className="field"><label htmlFor="edit-address">Address</label><input id="edit-address" name="address" defaultValue={school.address ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-contact-number">Contact number</label><input id="edit-contact-number" name="contact_number" defaultValue={school.contact_number ?? ""} /></div>
            <div className="field"><label htmlFor="edit-email">Email</label><input id="edit-email" name="email" type="email" defaultValue={school.email ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-website">Website</label><input id="edit-website" name="website" defaultValue={school.website ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-grades">Grades available</label><input id="edit-grades" name="grades_available" defaultValue={school.grades_available ?? ""} /></div>
            <div className="field">
              <label htmlFor="edit-board">Board</label>
              <select id="edit-board" name="board" defaultValue={school.board ?? ""}>
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <div className="field"><label htmlFor="edit-partnership-date">Partnership date</label><input id="edit-partnership-date" name="partnership_date" type="date" defaultValue={school.partnership_date ?? ""} /></div>
          <div className="field"><label htmlFor="edit-mou">Agreement / MoU reference</label><input id="edit-mou" name="mou_reference" defaultValue={school.mou_reference ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-bdm">Edusphere BDM</label><input id="edit-bdm" name="edusphere_bdm" defaultValue={school.edusphere_bdm ?? ""} /></div>
            <div className="field"><label htmlFor="edit-vp">Vice Principal</label><input id="edit-vp" name="vice_principal_name" defaultValue={school.vice_principal_name ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-visits">Monthly visit schedule</label><input id="edit-visits" name="monthly_visit_schedule" defaultValue={school.monthly_visit_schedule ?? ""} /></div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
        </form>
      )}
      {message && (
        <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
