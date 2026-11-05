"use client";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { DetailList } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import { sendRequest } from "@/lib/apiErrors";
import { CONTACT_ROLE_LABEL, type ContactRole } from "@/lib/bdmOrganizations";
import {
  type Batch, type CalendarEntry, CHANNEL_LABEL, CHANNELS, type College, collegeUrl, CONTACT_METHOD_LABEL, CONTACT_METHODS, type Course, dayText,
  EVENT_KIND_LABEL, EVENT_KINDS, isCollegeBody, type PlacementContact,
} from "@/lib/recruiterColleges";

const SERVER_FAILED = "Something went wrong on our side. Please try again.";
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" } as const;
type Method = "POST" | "PUT" | "PATCH" | "DELETE";

/** A blank box is null; whole numbers are sent as numbers, anything else as typed so the API's own message explains it. */
function whole(value: FormDataEntryValue | null): number | string | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  return /^-?\d+$/.test(text) ? Number(text) : text;
}
const text = (form: FormData, key: string) => String(form.get(key) ?? "");
const optional = (form: FormData, key: string) => text(form, key).trim() || null;

function Field({ id, label, children, grow = "1 1 180px" }: { id: string; label: string; children: ReactNode; grow?: string }) {
  return (
    <div className="field" style={{ flex: grow, margin: 0 }}>
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

function Multiline({ value }: { value: string | null }) {
  return value ? <span style={{ whiteSpace: "pre-line" }}>{value}</span> : <span className="muted">Not recorded</span>;
}

// pob-013 (DEC-SCOPE-410): a college's placement profile -- courses, graduating batches, the placement calendar, the drive process and
// eligibility rules, TPO office details and the TPO interaction log. The BDM owns the organization, MoU and commercials (P13), so none of
// them appear here. Every write re-renders from the college the API returns; `permissions.can_edit` decides the forms (the server enforces).
// `onNotice`: on the BDM organization page, success notices go to the page's one live region (bdm-009 QA9-01) instead of this section's.
export default function CollegePlacement({ orgId, initial = null, onNotice }: { orgId: string; initial?: College | null; onNotice?: (text: string) => void }) {
  const [college, setCollege] = useState<College | null>(initial);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ form: string; message: string } | null>(null);
  const [editingProfile, setEditingProfile] = useState(false);
  const [editingContact, setEditingContact] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const id = (part: string) => `college-${orgId}-${part}`;

  useEffect(() => {
    if (initial && version === 0) return; // the page already read it
    let live = true;
    setFailed(false);
    fetch(collegeUrl(orgId))
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !isCollegeBody(body)) throw new Error("not a college");
        if (live) setCollege(body.college);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [orgId, initial, version]);

  async function write(form: string, url: string, method: Method, body: unknown, done: string): Promise<boolean> {
    setBusy(form);
    setFailure(null);
    setNotice(null);
    const init: RequestInit = body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const outcome = await sendRequest(url, init);
    setBusy(null);
    if (outcome.ok && isCollegeBody(outcome.data)) {
      setCollege(outcome.data.college);
      if (onNotice) onNotice(done);
      else setNotice(done);
      return true;
    }
    const message = !outcome.ok ? ((outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message) : "Unable to save. Please try again.";
    setFailure({ form, message });
    return false;
  }

  /** A form's submit: reads its fields, sends, and clears the form only when the save succeeded. */
  const submitter = (form: string, method: Method, url: () => string, body: (data: FormData) => unknown, done: string, after?: () => void) =>
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const element = event.currentTarget;
      if (await write(form, url(), method, body(new FormData(element)), done)) {
        element.reset();
        after?.();
      }
    };

  const errorFor = (form: string) => failure?.form === form && <p className="form-error" role="alert">{failure.message}</p>;
  const titleId = id("title");

  if (failed) {
    return (
      <section className="action-card wide" aria-labelledby={titleId}>
        <h3 id={titleId}>Placement</h3>
        <p className="form-error">Unable to load the placement profile.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
      </section>
    );
  }
  if (!college) {
    return (
      <section className="action-card wide" aria-labelledby={titleId} aria-busy="true">
        <h3 id={titleId}>Placement</h3>
        <p className="muted">Loading the placement profile…</p>
      </section>
    );
  }

  const canEdit = college.permissions.can_edit;
  const remove = (kind: string, rowId: string, url: string, done: string, label: string) =>
    canEdit && (confirming === `${kind}-${rowId}` ? (
      <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
        <button type="button" className="btn small" disabled={busy !== null} onClick={() => void write(kind, url, "DELETE", undefined, done).then(() => setConfirming(null))}>
          {busy === kind ? "Removing…" : "Confirm remove"}
        </button>
        <button type="button" className="btn secondary small" onClick={() => setConfirming(null)}>Keep</button>
      </span>
    ) : (
      <button type="button" className="btn ghost small" aria-label={`Remove ${label}`} onClick={() => setConfirming(`${kind}-${rowId}`)}>Remove</button>
    ));

  const contactRow = (c: PlacementContact) => (
    <li key={c.id} style={{ marginBottom: 12 }}>
      <strong>{c.name}</strong>
      {c.is_primary && <span className="badge" style={{ marginLeft: 6 }}>Primary</span>}
      <div className="muted">
        {[c.designation, c.role ? CONTACT_ROLE_LABEL[c.role as ContactRole] : null, c.phone, c.email].filter(Boolean).join(" · ") || "No details"}
      </div>
      <div>Office: {c.office_details ?? <span className="muted">Not recorded</span>}</div>
      <div>Preferred contact: {c.preferred_contact_method ? CONTACT_METHOD_LABEL[c.preferred_contact_method] : <span className="muted">Not recorded</span>}</div>
      {canEdit && editingContact !== c.id && (
        <button type="button" className="btn secondary small" aria-label={`Edit TPO details for ${c.name}`} onClick={() => setEditingContact(c.id)}>Edit TPO details</button>
      )}
      {canEdit && editingContact === c.id && (
        <form className="form" noValidate style={ROW} aria-label={`TPO details for ${c.name}`}
          onSubmit={submitter("contact", "PATCH", () => collegeUrl(orgId, "contacts", c.id),
            (d) => ({ office_details: optional(d, "office_details"), preferred_contact_method: optional(d, "preferred_contact_method") }),
            "TPO details saved.", () => setEditingContact(null))}>
          <Field id={id(`office-${c.id}`)} label="Office details" grow="2 1 220px">
            <input id={id(`office-${c.id}`)} name="office_details" maxLength={300} defaultValue={c.office_details ?? ""} />
          </Field>
          <Field id={id(`method-${c.id}`)} label="Preferred contact method">
            <select id={id(`method-${c.id}`)} name="preferred_contact_method" defaultValue={c.preferred_contact_method ?? ""}>
              <option value="">Not recorded</option>
              {CONTACT_METHODS.map((m) => <option key={m} value={m}>{CONTACT_METHOD_LABEL[m]}</option>)}
            </select>
          </Field>
          <button type="submit" className="btn small" disabled={busy !== null}>{busy === "contact" ? "Saving…" : "Save"}</button>
          <button type="button" className="btn secondary small" onClick={() => setEditingContact(null)}>Cancel</button>
          {errorFor("contact")}
        </form>
      )}
    </li>
  );

  const batchRow = (b: Batch) => (
    <tr key={b.id}>
      <td data-label="Pass-out year">{b.pass_out_year}</td>
      <td data-label="Course">{b.course ?? "All courses"}</td>
      <td data-label="Pass-out date">{dayText(b.pass_out_date)}</td>
      <td data-label="Students">{b.student_count ?? "—"}</td>
      <td data-label="Notes" style={{ overflowWrap: "anywhere" }}>{b.notes ?? "—"}</td>
      {canEdit && <td data-label="Actions">{remove("batch", b.id, collegeUrl(orgId, "batches", b.id), "Batch removed.", `batch ${b.pass_out_year}`)}</td>}
    </tr>
  );

  const eventRow = (e: CalendarEntry) => (
    <tr key={e.id}>
      <td data-label="Dates" style={{ whiteSpace: "nowrap" }}>{dayText(e.starts_on)}{e.ends_on && e.ends_on !== e.starts_on ? ` – ${dayText(e.ends_on)}` : ""}</td>
      <td data-label="Entry" style={{ overflowWrap: "anywhere" }}>{e.title}</td>
      <td data-label="Kind">{EVENT_KIND_LABEL[e.kind] ?? e.kind}</td>
      <td data-label="Notes" style={{ overflowWrap: "anywhere" }}>{e.notes ?? "—"}</td>
      {canEdit && <td data-label="Actions">{remove("event", e.id, collegeUrl(orgId, "calendar", e.id), "Calendar entry removed.", e.title)}</td>}
    </tr>
  );

  const courseRow = (c: Course) => (
    <li key={c.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 6 }}>
      <span>{c.department ? `${c.department} · ` : ""}{c.course}</span>
      {remove("course", c.id, collegeUrl(orgId, "courses", c.id), "Course removed.", c.course)}
    </li>
  );

  return (
    <section className="action-card wide telecaller-list" aria-labelledby={titleId}>
      <h3 id={titleId}>Placement</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Relationship stage: {college.relationship_stage} · Assigned BDM: {college.assigned_bdm_name}
        {!canEdit && (college.archived ? " · This organization is archived, so its placement profile is read-only." : " · Read only")}
      </p>
      {!onNotice && <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>}

      <h4>Drive process and eligibility</h4>
      {editingProfile && canEdit ? (
        <form className="form" noValidate aria-label="Drive process and eligibility"
          onSubmit={submitter("profile", "PUT", () => collegeUrl(orgId, "profile"),
            (d) => ({ drive_process: optional(d, "drive_process"), eligibility_rules: optional(d, "eligibility_rules") }), "Placement profile saved.",
            () => setEditingProfile(false))}>
          <Field id={id("drive")} label="Drive process">
            <textarea id={id("drive")} name="drive_process" rows={3} maxLength={2000} defaultValue={college.profile.drive_process ?? ""} />
          </Field>
          <Field id={id("eligibility")} label="Eligibility rules">
            <textarea id={id("eligibility")} name="eligibility_rules" rows={3} maxLength={2000} defaultValue={college.profile.eligibility_rules ?? ""} />
          </Field>
          <div style={{ ...ROW, marginTop: 8 }}>
            <button type="submit" className="btn small" disabled={busy !== null}>{busy === "profile" ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" onClick={() => setEditingProfile(false)}>Cancel</button>
          </div>
          {errorFor("profile")}
        </form>
      ) : (
        <>
          <DetailList rows={[
            ["Drive process", <Multiline key="d" value={college.profile.drive_process} />],
            ["Eligibility rules", <Multiline key="e" value={college.profile.eligibility_rules} />],
          ]} />
          {college.profile.updated_at && (
            <p className="muted">Updated by {college.profile.updated_by_name} on <LocalTime value={college.profile.updated_at} /></p>
          )}
          {canEdit && <button type="button" className="btn secondary small" onClick={() => setEditingProfile(true)}>Edit drive process and eligibility</button>}
        </>
      )}

      <h4>TPO contacts</h4>
      {college.contacts.length === 0 ? <p className="empty">No contacts yet.</p> : <ul style={{ listStyle: "none", padding: 0 }}>{college.contacts.map(contactRow)}</ul>}

      <h4>Courses</h4>
      {college.courses_note && <p><span className="muted">Courses (BDM notes):</span> <Multiline value={college.courses_note} /></p>}
      {college.courses.length === 0 ? <p className="empty">No structured courses yet.</p> : <ul style={{ listStyle: "none", padding: 0 }}>{college.courses.map(courseRow)}</ul>}
      {errorFor("course")}
      {canEdit && (
        <form className="form" noValidate style={ROW} aria-label="Add a course"
          onSubmit={submitter("course-add", "POST", () => collegeUrl(orgId, "courses"),
            (d) => ({ department: optional(d, "department"), course: text(d, "course") }), "Course added.")}>
          <Field id={id("department")} label="Department (optional)">
            <input id={id("department")} name="department" maxLength={120} />
          </Field>
          <Field id={id("course")} label="Course">
            <input id={id("course")} name="course" maxLength={120} required />
          </Field>
          <button type="submit" className="btn small" disabled={busy !== null}>{busy === "course-add" ? "Adding…" : "Add course"}</button>
          {errorFor("course-add")}
        </form>
      )}

      <h4>Graduating batches</h4>
      {college.batches.length === 0 ? <p className="empty">No batches yet.</p> : (
        <div className="table-wrap" role="region" aria-label="Graduating batches" tabIndex={0}>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th scope="col">Pass-out year</th>
                <th scope="col">Course</th>
                <th scope="col">Pass-out date</th>
                <th scope="col">Students</th>
                <th scope="col">Notes</th>
                {canEdit && <th scope="col"><span className="visually-hidden">Actions</span></th>}
              </tr>
            </thead>
            <tbody>{college.batches.map(batchRow)}</tbody>
          </table>
        </div>
      )}
      {errorFor("batch")}
      {canEdit && (
        <form className="form" noValidate style={ROW} aria-label="Add a batch"
          onSubmit={submitter("batch-add", "POST", () => collegeUrl(orgId, "batches"),
            (d) => ({ pass_out_year: whole(d.get("pass_out_year")), course_id: optional(d, "course_id"), pass_out_date: optional(d, "pass_out_date"),
                      student_count: whole(d.get("student_count")), notes: optional(d, "notes") }), "Batch added.")}>
          <Field id={id("year")} label="Pass-out year" grow="0 1 130px">
            <input id={id("year")} name="pass_out_year" inputMode="numeric" required />
          </Field>
          <Field id={id("batch-course")} label="Course (optional)">
            <select id={id("batch-course")} name="course_id" defaultValue="">
              <option value="">All courses</option>
              {college.courses.map((c) => <option key={c.id} value={c.id}>{c.department ? `${c.department} · ` : ""}{c.course}</option>)}
            </select>
          </Field>
          <Field id={id("pass-date")} label="Pass-out date (optional)" grow="0 1 170px">
            <input id={id("pass-date")} name="pass_out_date" type="date" />
          </Field>
          <Field id={id("students")} label="Students (optional)" grow="0 1 130px">
            <input id={id("students")} name="student_count" inputMode="numeric" />
          </Field>
          <Field id={id("batch-notes")} label="Notes (optional)" grow="2 1 200px">
            <input id={id("batch-notes")} name="notes" maxLength={500} />
          </Field>
          <button type="submit" className="btn small" disabled={busy !== null}>{busy === "batch-add" ? "Adding…" : "Add batch"}</button>
          {errorFor("batch-add")}
        </form>
      )}

      <h4>Placement calendar</h4>
      {college.calendar.length === 0 ? <p className="empty">No calendar entries yet.</p> : (
        <div className="table-wrap" role="region" aria-label="Placement calendar" tabIndex={0}>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th scope="col">Dates</th>
                <th scope="col">Entry</th>
                <th scope="col">Kind</th>
                <th scope="col">Notes</th>
                {canEdit && <th scope="col"><span className="visually-hidden">Actions</span></th>}
              </tr>
            </thead>
            <tbody>{college.calendar.map(eventRow)}</tbody>
          </table>
        </div>
      )}
      {errorFor("event")}
      {canEdit && (
        <form className="form" noValidate style={ROW} aria-label="Add a calendar entry"
          onSubmit={submitter("event-add", "POST", () => collegeUrl(orgId, "calendar"),
            (d) => ({ title: text(d, "title"), kind: text(d, "kind"), starts_on: optional(d, "starts_on"), ends_on: optional(d, "ends_on"), notes: optional(d, "notes") }),
            "Calendar entry added.")}>
          <Field id={id("event-title")} label="Title" grow="2 1 200px">
            <input id={id("event-title")} name="title" maxLength={200} required />
          </Field>
          <Field id={id("event-kind")} label="Kind">
            <select id={id("event-kind")} name="kind" defaultValue="campus_drive">
              {EVENT_KINDS.map((k) => <option key={k} value={k}>{EVENT_KIND_LABEL[k]}</option>)}
            </select>
          </Field>
          <Field id={id("event-start")} label="Start date" grow="0 1 170px">
            <input id={id("event-start")} name="starts_on" type="date" required />
          </Field>
          <Field id={id("event-end")} label="End date (optional)" grow="0 1 170px">
            <input id={id("event-end")} name="ends_on" type="date" />
          </Field>
          <Field id={id("event-notes")} label="Notes (optional)" grow="2 1 200px">
            <input id={id("event-notes")} name="notes" maxLength={500} />
          </Field>
          <button type="submit" className="btn small" disabled={busy !== null}>{busy === "event-add" ? "Adding…" : "Add entry"}</button>
          {errorFor("event-add")}
        </form>
      )}

      <h4>TPO interactions</h4>
      {canEdit && (
        <form className="form" noValidate aria-label="Log a TPO interaction"
          onSubmit={submitter("interaction", "POST", () => collegeUrl(orgId, "interactions"),
            (d) => {
              const when = text(d, "occurred_at");
              return { channel: text(d, "channel"), occurred_at: when ? new Date(when).toISOString() : null, contact_id: optional(d, "contact_id"),
                       summary: text(d, "summary"), next_step: optional(d, "next_step") };
            }, "Interaction logged.")}>
          <div style={ROW}>
            <Field id={id("channel")} label="Channel">
              <select id={id("channel")} name="channel" defaultValue="meeting">
                {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
              </select>
            </Field>
            <Field id={id("when")} label="When">
              <input id={id("when")} name="occurred_at" type="datetime-local" required />
            </Field>
            <Field id={id("with")} label="With (optional)">
              <select id={id("with")} name="contact_id" defaultValue="">
                <option value="">Not recorded</option>
                {college.contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          </div>
          <Field id={id("summary")} label="Summary">
            <textarea id={id("summary")} name="summary" rows={3} maxLength={2000} required />
          </Field>
          <Field id={id("next")} label="Next step (optional)">
            <input id={id("next")} name="next_step" maxLength={500} />
          </Field>
          <button type="submit" className="btn small" style={{ marginTop: 8 }} disabled={busy !== null}>{busy === "interaction" ? "Logging…" : "Log interaction"}</button>
          {errorFor("interaction")}
        </form>
      )}
      {college.interactions.length === 0 ? <p className="empty">No TPO interactions yet.</p> : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {college.interactions.map((i) => (
            <li key={i.id} style={{ borderTop: "1px solid var(--line, #e5e7eb)", padding: "8px 0" }}>
              <div><strong>{CHANNEL_LABEL[i.channel] ?? i.channel}</strong>{i.contact_name ? ` with ${i.contact_name}` : ""} · <LocalTime value={i.occurred_at} /></div>
              <div style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{i.summary}</div>
              {i.next_step && <div><span className="muted">Next step:</span> {i.next_step}</div>}
              <div className="muted" style={{ fontSize: 13 }}>Logged by {i.logged_by_name}</div>
            </li>
          ))}
        </ul>
      )}
      {college.interaction_total > college.interactions.length && (
        <p className="muted">Showing the latest {college.interactions.length} of {college.interaction_total} interactions.</p>
      )}

      <h4>Campus drives</h4>
      {college.drives.length === 0 ? <p className="empty">No campus drives at this college yet.</p> : (
        <ul style={{ paddingLeft: 18 }}>
          {college.drives.map((d) => <li key={d.id}>{d.drive_code} · {dayText(d.drive_date)} · {d.job_role} · {d.status}</li>)}
        </ul>
      )}
    </section>
  );
}
