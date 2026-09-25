"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import TierDowngradeConfirm, { type TierService } from "@/components/TierDowngradeConfirm";
import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import { type Feedback, toneClass } from "@/lib/welcomeLink";

type School = {
  id: string; school_code: string | null; name: string;
  branch: string | null; address: string | null; contact_number: string | null;
  email: string | null; website: string | null; grades_available: string | null;
  board: string | null; partnership_date: string | null; mou_reference: string | null;
  edusphere_bdm: string | null; monthly_visit_schedule: string | null; vice_principal_name: string | null;
  tier?: string | null; tier_valid_until?: string | null;
};

type TierChange = { direction: "upgrade" | "downgrade" | "unchanged"; from_tier: string | null; to_tier: string | null; gained: TierService[]; lost: TierService[] };
type Body = Record<string, string | null>;

const FIELDS = ["branch", "address", "contact_number", "email", "website", "grades_available", "board", "partnership_date", "mou_reference", "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name", "tier", "tier_valid_until"] as const;
const SAVE_ID = "edit-save-btn";

const tierName = (tier: string | null | undefined) => (tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : "no partnership tier");

function savedText(change: TierChange | null | undefined): string {
  if (!change || change.direction === "unchanged") return "School profile updated.";
  const gained = change.direction === "upgrade" && change.gained.length ? `; newly available: ${change.gained.map((s) => s.label).join(", ")}` : "";
  return `School profile updated. Partnership is now ${tierName(change.to_tier)}${gained}.`;
}

// ENH-009 / DEC-SCOPE-025: lookup-by-code then PATCH, mirroring the existing
// GET .../school-students/lookup?code= convention (admin.py:1240) -- the codebase has no
// clickable-table-row-to-edit pattern anywhere, and the established convention is "read via the
// generic portal section, write via a dedicated panel" (same split as AdminSchoolCreatePanel.tsx).
// ENH-023 / DEC-SCOPE-030: the tier is edited here too. A changed tier is previewed first; a downgrade or removal is only
// saved after the admin confirms the services the school loses (D7), and every tier save carries `expected_tier` (D12).
export default function AdminSchoolEditPanel() {
  const [busy, setBusy] = useState<null | "lookup" | "checking" | "saving">(null);
  const [message, setMessage] = useState<Feedback | null>(null);
  const [school, setSchool] = useState<School | null>(null);
  const [pending, setPending] = useState<{ body: Body; change: TierChange } | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const focusMessage = useRef(false);

  // An outcome after a save attempt takes focus (ENH-004's pattern): the control that started it may be disabled or gone.
  useEffect(() => {
    if (message && focusMessage.current) {
      focusMessage.current = false;
      messageRef.current?.focus();
    }
  }, [message]);

  function report(next: Feedback) {
    focusMessage.current = true;
    setMessage(next);
  }

  function cancelDowngrade() {
    setPending(null);
    refocus(SAVE_ID);
  }

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    setBusy("lookup");
    setMessage(null);
    setSchool(null);
    setPending(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/lookup?code=${encodeURIComponent(String(code))}`);
    } catch {
      setBusy(null);
      setMessage({ text: "Network error -- check your connection and try again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail, "Unable to look up that school."), tone: "error" });
      return;
    }
    setSchool(data as School);
  }

  async function preview(current: School, tier: string | null): Promise<TierChange | null> {
    setBusy("checking");
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${current.id}/tier-change-preview?tier=${encodeURIComponent(tier ?? "")}`);
    } catch {
      setBusy(null);
      report({ text: "Network error -- nothing was saved. Check your connection and try again.", tone: "error" });
      return null;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      report({ text: detailMessage(data.detail, "Unable to check the tier change. Nothing was saved."), tone: "error" });
      return null;
    }
    return data as TierChange;
  }

  async function patch(current: School, body: Body) {
    setBusy("saving");
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${current.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      setBusy(null);
      setPending(null);
      report({ text: "Network error -- it is not known whether the changes saved. Look the school up again before retrying.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    setPending(null);
    if (!response.ok) {
      // QA-023-04: a 4xx is refused before any commit, so nothing was saved; a 5xx can fail after the commit, so the
      // outcome is unknown and the admin is told to check rather than retry blindly.
      report({ text: response.status >= 500 ? "The save could not be confirmed. Look the school up again to check before retrying." : `Not saved: ${detailMessage(data.detail)}`, tone: "error" });
      return;
    }
    if (!isRequestBody(data)) {
      report({ text: "The save could not be confirmed. Look the school up again before changing anything else.", tone: "error" });
      return;
    }
    setSchool(data as School);
    report({ text: savedText((data as { tier_change?: TierChange | null }).tier_change), tone: "success" });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    const form = new FormData(event.currentTarget);
    // Diff against the loaded school, so only genuinely-changed fields are sent: an emptied
    // field goes as an explicit `null` (the backend's `exclude_unset=True` clears it), and an
    // untouched field is omitted entirely -- otherwise the `school.profile_update` audit row's
    // `changed_fields` would list all 12 fields on every save (final-review finding, ENH-009),
    // and an untouched tier would write a `school.tier_update` row (ENH-023).
    const body: Body = {};
    for (const field of FIELDS) {
      const raw = String(form.get(field) ?? "").trim();
      const next = raw === "" ? null : raw;
      const current = field === "tier" ? school.tier || null : (school[field] ?? null);
      if (next !== current) body[field] = next;
    }
    setMessage(null);
    setPending(null);
    if (Object.keys(body).length === 0) {
      report({ text: "No changes to save.", tone: "success" }); // QA-023-05: no empty PATCH, no misleading "updated"
      return;
    }
    if ("tier" in body) {
      // D12: the tier this admin looked at. If it moved since, the server answers 409 instead of applying a change the
      // admin never confirmed. A stored "" (legacy row, D13) counts as no tier, same as the diff baseline above.
      body.expected_tier = school.tier || null;
      const change = await preview(school, body.tier);
      if (!change) return;
      if (change.direction === "downgrade") {
        setPending({ body, change });
        return;
      }
    }
    await patch(school, body);
  }

  const isBusy = busy !== null;
  return (
    <div className="action-card">
      <h3>Edit school profile</h3>
      <form className="form" onSubmit={lookup}>
        <div className="field">
          <label htmlFor="school-lookup-code">School ID</label>
          <input id="school-lookup-code" name="code" required />
        </div>
        <button className="btn" disabled={isBusy}>{busy === "lookup" ? "Looking up…" : "Look up"}</button>
      </form>
      {school && (
        <form className="form" onSubmit={save} onChange={() => setPending(null)} aria-busy={isBusy} style={{ marginTop: 16 }}>
          <p className="muted">{school.name} ({school.school_code})</p>
          <div className="field"><label htmlFor="edit-branch">Branch</label><input id="edit-branch" name="branch" defaultValue={school.branch ?? ""} disabled={isBusy} /></div>
          <div className="field"><label htmlFor="edit-address">Address</label><input id="edit-address" name="address" defaultValue={school.address ?? ""} disabled={isBusy} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-contact-number">Contact number</label><input id="edit-contact-number" name="contact_number" defaultValue={school.contact_number ?? ""} disabled={isBusy} /></div>
            <div className="field"><label htmlFor="edit-email">Email</label><input id="edit-email" name="email" type="email" defaultValue={school.email ?? ""} disabled={isBusy} /></div>
          </div>
          <div className="field"><label htmlFor="edit-website">Website</label><input id="edit-website" name="website" defaultValue={school.website ?? ""} disabled={isBusy} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-grades">Grades available</label><input id="edit-grades" name="grades_available" defaultValue={school.grades_available ?? ""} disabled={isBusy} /></div>
            <div className="field">
              <label htmlFor="edit-board">Board</label>
              <select id="edit-board" name="board" defaultValue={school.board ?? ""} disabled={isBusy}>
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <div className="field"><label htmlFor="edit-partnership-date">Partnership date</label><input id="edit-partnership-date" name="partnership_date" type="date" defaultValue={school.partnership_date ?? ""} disabled={isBusy} /></div>
          <div className="field"><label htmlFor="edit-mou">Agreement / MoU reference</label><input id="edit-mou" name="mou_reference" defaultValue={school.mou_reference ?? ""} disabled={isBusy} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-bdm">Edusphere BDM</label><input id="edit-bdm" name="edusphere_bdm" defaultValue={school.edusphere_bdm ?? ""} disabled={isBusy} /></div>
            <div className="field"><label htmlFor="edit-vp">Vice Principal</label><input id="edit-vp" name="vice_principal_name" defaultValue={school.vice_principal_name ?? ""} disabled={isBusy} /></div>
          </div>
          <div className="field"><label htmlFor="edit-visits">Monthly visit schedule</label><input id="edit-visits" name="monthly_visit_schedule" defaultValue={school.monthly_visit_schedule ?? ""} disabled={isBusy} /></div>
          <fieldset className="question">
            <legend>Partnership</legend>
            {/* QA-023-02: top-align the pair; stretching to the help line's height made the select grow and drop 16px. */}
            <div className="form-grid" style={{ alignItems: "start" }}>
              <div className="field">
                <label htmlFor="edit-tier">Partnership tier</label>
                <select id="edit-tier" name="tier" defaultValue={school.tier ?? ""} aria-describedby="edit-tier-help" disabled={isBusy}>
                  <option value="">Not set</option>
                  <option value="bronze">Bronze</option>
                  <option value="silver">Silver</option>
                  <option value="gold">Gold</option>
                  <option value="platinum">Platinum</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="edit-tier-valid-until">Valid until</label>
                <input id="edit-tier-valid-until" name="tier_valid_until" type="date" defaultValue={school.tier_valid_until ?? ""} aria-describedby="edit-tier-valid-help" disabled={isBusy} />
                <span id="edit-tier-valid-help" className="muted">Leave empty for no end date.</span>
              </div>
            </div>
            <p id="edit-tier-help" className="muted">Currently {tierName(school.tier)}. Changing it notifies the school; a downgrade asks you to confirm first.</p>
          </fieldset>
          <button id={SAVE_ID} className="btn" disabled={isBusy}>{busy === "checking" ? "Checking tier change…" : busy === "saving" && !pending ? "Saving…" : "Save changes"}</button>
          {pending && (
            <TierDowngradeConfirm
              schoolName={school.name}
              fromTier={tierName(pending.change.from_tier)}
              toTier={tierName(pending.change.to_tier)}
              lost={pending.change.lost}
              busy={isBusy}
              onConfirm={() => void patch(school, pending.body)}
              onCancel={cancelDowngrade}
            />
          )}
        </form>
      )}
      {message && (
        <div ref={messageRef} tabIndex={-1} className={toneClass[message.tone]} role={message.tone === "error" ? "alert" : "status"} aria-live={message.tone === "error" ? "assertive" : "polite"} style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
