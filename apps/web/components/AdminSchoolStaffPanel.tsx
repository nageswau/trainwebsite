"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type SchoolOption = { id: string; name: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to create this account.";
}

// SCH-004/005/006 (DEC-SCOPE-014): only Overseas Admin/Super Admin creates an
// academic_team/career_counselor/psychometric_team account -- a separate path from
// SCH-003's Coordinator-issued invites, since these are internal EduSphere staff, not
// external school-side accounts. Same "dedicated create panel next to the generic
// read-only portal section" split already established for schools/universities.
export default function AdminSchoolStaffPanel() {
  const router = useRouter();
  const [schools, setSchools] = useState<SchoolOption[]>([]);
  const [selectedSchools, setSelectedSchools] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/overseas-admin/schools")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: SchoolOption[]) => !cancelled && setSchools(data))
      .catch(() => !cancelled && setSchools([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/overseas-admin/school-staff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: form.get("role"),
        full_name: form.get("full_name"),
        email: form.get("email"),
        school_ids: selectedSchools,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `Account created for ${data.email} (default password: ChangeMe@12345 -- share it securely and ask them to change it).`, failed: false });
    formElement.reset();
    setSelectedSchools([]);
    router.refresh();
  }

  function toggleSchool(id: string) {
    setSelectedSchools((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  }

  return (
    <div className="action-card">
      <h3>Create Academic Team / Career Counselor / Psychometric Team account</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="staff-role">Role</label>
          <select id="staff-role" name="role" required defaultValue="">
            <option value="" disabled>Select role</option>
            <option value="academic_team">Academic Team</option>
            <option value="career_counselor">Career Counselor</option>
            <option value="psychometric_team">Psychometric Team</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="staff-name">Full name</label>
          <input id="staff-name" name="full_name" required />
        </div>
        <div className="field">
          <label htmlFor="staff-email">Email</label>
          <input id="staff-email" name="email" type="email" required />
        </div>
        <div className="field full">
          <span>School portfolio</span>
          {schools.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No partner schools yet -- create one first.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {schools.map((s) => (
                <label key={s.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox" checked={selectedSchools.includes(s.id)} onChange={() => toggleSchool(s.id)} />
                  {s.name}
                </label>
              ))}
            </div>
          )}
          <span className="muted" style={{ fontSize: 12 }}>A portfolio can be left empty and filled in later, but the account can&apos;t act on any student until at least one school is assigned.</span>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
