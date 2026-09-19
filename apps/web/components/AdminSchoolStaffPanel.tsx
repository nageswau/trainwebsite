"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { type Feedback, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

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
  const [schoolQuery, setSchoolQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Feedback | null>(null);

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
    let response: Response;
    try {
      response = await fetch("/api/v1/overseas-admin/school-staff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: form.get("role"),
          full_name: form.get("full_name"),
          email: form.get("email"),
          school_ids: selectedSchools,
        }),
      });
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- it is not known whether the account was created. Check the Users list before trying again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    setMessage(welcomeLinkFeedback(`Account created for ${data.email}.`, data));
    formElement.reset();
    setSelectedSchools([]);
    setSchoolQuery("");
    router.refresh();
  }

  const normalizedQuery = schoolQuery.trim().toLowerCase();
  const visibleSchools = normalizedQuery ? schools.filter((s) => s.name.toLowerCase().includes(normalizedQuery)) : schools;

  function handleSchoolSelectionChange(event: ChangeEvent<HTMLSelectElement>) {
    // Filtering hides <option> elements rather than removing them from state, so a
    // school selected before a search narrowed the list must not be silently dropped --
    // keep whatever's already selected among the schools currently hidden by the search,
    // and take the browser's own selection state only for the ones actually on screen.
    const visibleIds = new Set(visibleSchools.map((s) => s.id));
    const chosenFromVisible = Array.from(event.target.selectedOptions, (option) => option.value);
    setSelectedSchools((current) => [...current.filter((id) => !visibleIds.has(id)), ...chosenFromVisible]);
  }

  function selectAll() {
    setSelectedSchools(schools.map((s) => s.id));
  }

  function selectVisible() {
    const visibleIds = visibleSchools.map((s) => s.id);
    setSelectedSchools((current) => Array.from(new Set([...current, ...visibleIds])));
  }

  function clearVisible() {
    const visibleIds = new Set(visibleSchools.map((s) => s.id));
    setSelectedSchools((current) => current.filter((id) => !visibleIds.has(id)));
  }

  function clearAll() {
    setSelectedSchools([]);
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
          <label htmlFor="staff-schools">School portfolio {selectedSchools.length > 0 && <span className="muted">({selectedSchools.length} selected)</span>}</label>
          {schools.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No partner schools yet -- create one first.</p>
          ) : (
            <>
              <input
                type="search"
                className="search"
                placeholder="Search schools…"
                value={schoolQuery}
                onChange={(event) => setSchoolQuery(event.target.value)}
                style={{ marginBottom: 8 }}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                <button type="button" className="btn ghost small" onClick={selectAll}>Select all ({schools.length})</button>
                <button type="button" className="btn ghost small" onClick={selectVisible} disabled={visibleSchools.length === 0}>
                  Select visible {normalizedQuery ? `(${visibleSchools.length})` : ""}
                </button>
                <button type="button" className="btn ghost small" onClick={clearVisible} disabled={visibleSchools.length === 0}>Clear visible</button>
                <button type="button" className="btn ghost small" onClick={clearAll} disabled={selectedSchools.length === 0}>Clear all</button>
              </div>
              {visibleSchools.length === 0 ? (
                <p className="muted" style={{ fontSize: 13 }}>No schools match &quot;{schoolQuery}&quot;.</p>
              ) : (
                <select
                  id="staff-schools"
                  className="select"
                  multiple
                  size={Math.min(visibleSchools.length, 8)}
                  value={selectedSchools}
                  onChange={handleSchoolSelectionChange}
                >
                  {visibleSchools.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              )}
            </>
          )}
          <span className="muted" style={{ fontSize: 12 }}>Hold Ctrl (Windows) or Cmd (Mac) to select more than one. A portfolio can be left empty and filled in later, but the account can&apos;t act on any student until at least one school is assigned.</span>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      {message && (
        <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
