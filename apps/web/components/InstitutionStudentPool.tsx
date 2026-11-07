"use client";
import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import {
  applicationLabel, ASSIGNEES_URL, importPath, isPool, NOTICE_LABEL, type Permission, type PermissionUser, permissionsUrl, poolUrl, PURPOSE_LABEL, PURPOSES,
  STATUS_LABEL, type StudentPool,
} from "@/lib/institutionPool";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";
import { dayText } from "@/lib/recruiterColleges";

const SERVER_FAILED = "Something went wrong on our side. Please try again.";
const PAGE = 25;
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" } as const;
type Filters = { permission_id: string; pass_out_year: string; course: string; q: string };
const NO_FILTERS: Filters = { permission_id: "", pass_out_year: "", course: "", q: "" };

/** S3: the people a permission names -- picked from the active candidate workers (the task-assignee lookup). */
function PeoplePicker({ id, chosen, onChange }: { id: string; chosen: PermissionUser[]; onChange: (next: PermissionUser[]) => void }) {
  const [q, setQ] = useState("");
  const [options, setOptions] = useState<PermissionUser[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${ASSIGNEES_URL}?q=${encodeURIComponent(q)}`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error("lookup");
        setOptions((await r.json()) as PermissionUser[]);
        setFailed(false);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [q]);
  const picked = new Set(chosen.map((u) => u.id));
  const shown = [...chosen, ...(options ?? []).filter((u) => !picked.has(u.id))];
  const toggle = (person: PermissionUser) => onChange(picked.has(person.id) ? chosen.filter((u) => u.id !== person.id) : [...chosen, person]);
  return (
    <fieldset className="field" style={{ margin: 0 }}>
      <legend>People who may see these students</legend>
      <label htmlFor={`${id}-q`} className="visually-hidden">Find a person</label>
      <input id={`${id}-q`} type="search" placeholder="Find a person" value={q} onChange={(e) => setQ(e.target.value)} />
      {failed && <p className="form-error">People could not be loaded. Try again.</p>}
      <div style={{ maxHeight: 180, overflowY: "auto", marginTop: 4 }}>
        {shown.map((person) => (
          <label key={person.id} style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: "normal" }}>
            <input type="checkbox" checked={picked.has(person.id)} onChange={() => toggle(person)} /> {person.full_name}
          </label>
        ))}
        {options && shown.length === 0 && <p className="muted">No one matches.</p>}
      </div>
    </fieldset>
  );
}

/** QA-01: what is missing, in plain words, before anything is sent (the server checks the same and more). */
export function permissionProblems(body: Record<string, unknown>, creating: boolean): string {
  const problems = [
    creating && !String(body.agreement_reference ?? "").trim() && "Enter the agreement reference.",
    (!body.valid_from || !body.expires_on) && "Choose the start and expiry dates.",
    body.valid_from && body.expires_on && String(body.expires_on) < String(body.valid_from) && "The expiry date must be on or after the start date.",
    !(body.purposes as string[]).length && "Choose at least one permitted purpose.",
    !(body.user_ids as string[]).length && "Choose at least one person.",
  ];
  return problems.filter(Boolean).join(" ");
}

/** Create (every field) or edit (window, purposes, people, notes) one permission. */
function PermissionForm({ orgId, editing, busy, onSubmit, onInvalid, onCancel }: {
  orgId: string; editing: Permission | null; busy: boolean; onSubmit: (body: Record<string, unknown>) => void; onInvalid: (message: string) => void;
  onCancel: () => void;
}) {
  const [people, setPeople] = useState<PermissionUser[]>(editing?.users ?? []);
  const id = `pool-${orgId}-${editing?.id ?? "new"}`;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      purposes: form.getAll("purposes").map(String), valid_from: String(form.get("valid_from") ?? ""), expires_on: String(form.get("expires_on") ?? ""),
      notes: String(form.get("notes") ?? "").trim() || null, user_ids: people.map((u) => u.id),
    };
    if (!editing) body.agreement_reference = String(form.get("agreement_reference") ?? "");
    const problem = permissionProblems(body, !editing);
    if (problem) onInvalid(problem);
    else onSubmit(body);
  }
  return (
    <form className="form" onSubmit={submit} noValidate aria-label={editing ? `Change ${editing.agreement_reference}` : "Add a data permission"}>
      <div style={ROW}>
        {!editing && (
          <div className="field" style={{ flex: "1 1 200px", margin: 0 }}>
            <label htmlFor={`${id}-ref`}>Agreement reference</label>
            <input id={`${id}-ref`} name="agreement_reference" maxLength={100} required />
          </div>
        )}
        <div className="field" style={{ flex: "1 1 150px", margin: 0 }}>
          <label htmlFor={`${id}-from`}>Valid from</label>
          <input id={`${id}-from`} name="valid_from" type="date" required defaultValue={editing?.valid_from} />
        </div>
        <div className="field" style={{ flex: "1 1 150px", margin: 0 }}>
          <label htmlFor={`${id}-to`}>Expires on</label>
          <input id={`${id}-to`} name="expires_on" type="date" required defaultValue={editing?.expires_on} />
        </div>
      </div>
      <fieldset className="field" style={{ margin: "8px 0 0" }}>
        <legend>Permitted purposes</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {PURPOSES.map((p) => (
            <label key={p} style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: "normal" }}>
              <input type="checkbox" name="purposes" value={p} defaultChecked={editing ? editing.purposes.includes(p) : p === "placement"} /> {PURPOSE_LABEL[p]}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field" style={{ margin: "8px 0 0" }}>
        <label htmlFor={`${id}-notes`}>Notes</label>
        <textarea id={`${id}-notes`} name="notes" maxLength={500} rows={2} defaultValue={editing?.notes ?? ""} />
      </div>
      <PeoplePicker id={id} chosen={people} onChange={setPeople} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        <button className="btn small" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Add permission"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function PermissionRow({ permission, canManage, listed, orgId, onEdit, onRevoke, busy }: {
  permission: Permission; canManage: boolean; listed: boolean; orgId: string; onEdit: () => void; onRevoke: () => void; busy: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const open = permission.status !== "revoked";
  return (
    <tr>
      <td data-label="Agreement">{permission.agreement_reference}{permission.notes && <div className="muted" style={{ whiteSpace: "pre-line" }}>{permission.notes}</div>}</td>
      <td data-label="Purposes">{permission.purposes.map((p) => PURPOSE_LABEL[p] ?? p).join(", ")}</td>
      <td data-label="Valid">{dayText(permission.valid_from)} – {dayText(permission.expires_on)}</td>
      <td data-label="Status"><span className="badge">{STATUS_LABEL[permission.status]}</span></td>
      <td data-label="People">{permission.users.map((u) => u.full_name).join(", ")}</td>
      <td data-label="Students">{permission.student_count.toLocaleString("en-IN")}</td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {permission.status === "active" && listed && <Link className="btn small" href={importPath(orgId, permission.id)}>Import students</Link>}
          {canManage && open && <button type="button" className="btn secondary small" onClick={onEdit} disabled={busy}>Change</button>}
          {canManage && open && !confirming && (
            <button type="button" className="btn secondary small" onClick={() => setConfirming(true)} disabled={busy}>Revoke</button>
          )}
          {confirming && (
            <span role="group" aria-label="Confirm revoke" style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span>Hide its students from everyone?</span>
              <button type="button" className="btn small" onClick={onRevoke} disabled={busy}>Yes, revoke</button>
              <button type="button" className="btn secondary small" onClick={() => setConfirming(false)} disabled={busy}>Keep</button>
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

// pob-014 (DEC-SCOPE-425): a college's institution data permissions and the students they cover. The API lists only the students the
// viewer may see now (S6) and only the permissions that name them (a placement manager sees all, S10); this section never decides access.
export default function InstitutionStudentPool({ orgId, viewerId }: { orgId: string; viewerId: string }) {
  const [pool, setPool] = useState<StudentPool | null>(null);
  const [failed, setFailed] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [form, setForm] = useState<"new" | string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const titleId = `pool-${orgId}-title`;

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    for (const [key, value] of Object.entries(filters)) if (value.trim()) params.set(key, value.trim());
    setFailed(false);
    fetch(`${poolUrl(orgId)}?${params}`, { signal: controller.signal })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !isPool(body)) throw new Error("pool");
        setPool(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [orgId, filters, offset, version]);

  async function save(url: string, method: "POST" | "PATCH", body: unknown, done: string) {
    setBusy(true);
    setError("");
    setNotice("");
    const init: RequestInit = { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) };
    const outcome = await sendRequest(url, init);
    setBusy(false);
    if (!outcome.ok) return setError((outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message);
    setForm(null);
    setNotice(done);
    setVersion((v) => v + 1);
  }

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const year = String(data.get("pass_out_year") ?? "").trim();
    if (year && !(year.length === 4 && Number.isInteger(Number(year)) && Number(year) >= 2000 && Number(year) <= 2100)) return setError("Enter a pass-out year from 2000 to 2100."); // QA-02
    setError("");
    setOffset(0);
    setFilters({ permission_id: String(data.get("permission_id") ?? ""), pass_out_year: String(data.get("pass_out_year") ?? ""),
                 course: String(data.get("course") ?? ""), q: String(data.get("q") ?? "") });  // prettier-ignore
  }

  if (failed && !pool) {
    return (
      <section className="action-card wide institution-pool" aria-labelledby={titleId}>
        <h3 id={titleId}>Institution student pool</h3>
        <p className="form-error">Unable to load the student pool.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
      </section>
    );
  }
  if (!pool) {
    return (
      <section className="action-card wide" aria-labelledby={titleId} aria-busy="true">
        <h3 id={titleId}>Institution student pool</h3>
        <p className="muted">Loading the student pool…</p>
      </section>
    );
  }
  const editing = pool.permissions.find((p) => p.id === form) ?? null;
  const { items, total } = pool.students;
  const filtered = Object.values(filters).some((v) => v.trim());
  return (
    <section className="action-card wide institution-pool" aria-labelledby={titleId}>
      <h3 id={titleId}>Institution student pool</h3>
      <p className="muted">
        Students this college supplied under a data permission. Only the people a permission names see its students, and only while it is
        in force; once it expires or is revoked they are hidden and cannot be shared.
      </p>
      <p className={notice ? "form-message" : "visually-hidden"} role="status" aria-live="polite">{notice}</p>
      {error && <p className="form-error" role="alert">{error}</p>}

      <h4>Data permissions</h4>
      {pool.permissions.length === 0 ? (
        <p className="muted">{pool.can_manage ? "No data permission is recorded for this college yet." : "No data permission names you for this college."}</p>
      ) : (
        <div className="table-wrap">
          <table className="table compact stack" aria-label="Data permissions">
            <thead><tr><th>Agreement</th><th>Purposes</th><th>Valid</th><th>Status</th><th>People</th><th>Students</th><th>Actions</th></tr></thead>
            <tbody>
              {pool.permissions.map((p) => (
                <PermissionRow key={p.id} permission={p} orgId={orgId} canManage={pool.can_manage} listed={p.users.some((u) => u.id === viewerId)} busy={busy}
                  onEdit={() => setForm(p.id)} onRevoke={() => save(permissionsUrl(orgId, p.id, "revoke"), "POST", undefined, "Permission revoked.")} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pool.can_manage && form === null && (
        <div style={{ display: "flex", marginTop: 8 }}>{/* QA-03: a compact button, not the card's width */}
          <button type="button" className="btn secondary small" onClick={() => setForm("new")}>Add a data permission</button>
        </div>
      )}
      {pool.can_manage && form !== null && (
        <PermissionForm key={form} orgId={orgId} editing={editing} busy={busy} onCancel={() => setForm(null)} onInvalid={(m) => { setNotice(""); setError(m); }}
          onSubmit={(body) => (editing ? save(permissionsUrl(orgId, editing.id), "PATCH", body, "Permission updated.") : save(permissionsUrl(orgId), "POST", body, "Permission added."))} />
      )}

      <h4 style={{ marginTop: 16 }}>Students</h4>
      <form className="form" onSubmit={filter} role="search" aria-label="Filter students" style={ROW}>
        <div className="field" style={{ flex: "1 1 180px", margin: 0 }}>
          <label htmlFor={`${titleId}-perm`}>Permission</label>
          <select id={`${titleId}-perm`} name="permission_id" defaultValue={filters.permission_id}>
            <option value="">All</option>
            {pool.permissions.map((p) => <option key={p.id} value={p.id}>{p.agreement_reference}</option>)}
          </select>
        </div>
        <div className="field" style={{ flex: "0 1 120px", margin: 0 }}>
          <label htmlFor={`${titleId}-year`}>Pass-out year</label>
          <input id={`${titleId}-year`} name="pass_out_year" inputMode="numeric" maxLength={4} defaultValue={filters.pass_out_year} />
        </div>
        <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
          <label htmlFor={`${titleId}-course`}>Course</label>
          <input id={`${titleId}-course`} name="course" maxLength={120} defaultValue={filters.course} />
        </div>
        <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
          <label htmlFor={`${titleId}-q`}>Name or code</label>
          <input id={`${titleId}-q`} name="q" maxLength={200} defaultValue={filters.q} />
        </div>
        <button className="btn small">Filter</button>
      </form>
      {failed && <p className="form-error" role="alert">Unable to load the students. Check the filters and try again.</p>}
      {items.length === 0 ? (
        <p className="muted" style={{ marginTop: 8 }}>{filtered ? "No students match these filters." : "No students to show."}</p>
      ) : (
        <>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="table compact stack" aria-label="Students">
              <thead><tr><th>Student</th><th>Pass-out year</th><th>Course</th><th>Notice</th><th>Placement status</th></tr></thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id}>
                    <td data-label="Student">
                      <span style={{ overflowWrap: "anywhere" }}>
                        <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(s.id)}`}>{s.candidate_code}</Link> {s.name}
                      </span>
                    </td>
                    <td data-label="Pass-out year">{s.passing_year ?? "—"}</td>
                    <td data-label="Course">{s.qualification ?? "—"}</td>
                    <td data-label="Notice">{s.notice_status ? NOTICE_LABEL[s.notice_status] : "—"}</td>
                    <td data-label="Placement status">{applicationLabel(s.placement_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
            <span className="muted">{offset + 1}–{offset + items.length} of {total.toLocaleString("en-IN")}</span>
            <button type="button" className="btn secondary small" onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}>Previous</button>
            <button type="button" className="btn secondary small" onClick={() => setOffset(offset + PAGE)} disabled={offset + items.length >= total}>Next</button>
          </div>
        </>
      )}
    </section>
  );
}
