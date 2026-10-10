"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { formatCalendarDate } from "@/lib/formatDate";
import { signatorySearch } from "@/lib/universityAgreements";
import {
  conflictMessage,
  isOnboardingPage,
  type OnboardingItem,
  type OnboardingPage,
  type OnboardingStatus,
  onboardingUrl,
  STATUS_LABEL,
  STATUSES,
} from "@/lib/universityOnboarding";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Values = { status: OnboardingStatus; owner_user_id: string; due_date: string; note: string };
const STATUS_CLASS: Record<OnboardingStatus, string> = { completed: "status", in_progress: "badge", not_started: "status pending" };

// upc-027 (spec §4): §29's partner onboarding checklist. Before an agreement is signed it only says so (OB3). Once started, each item
// shows its status as text, owner, due date, completion and note; those who may edit change one item at a time in a form below the table.
// The API enforces every rule (scope, started, Lost, owner, note length) and returns the whole checklist; a refusal keeps what was typed.
// "Course database updated" completes itself from the course master (OB7), so its form offers no status. When the save completes the
// checklist the API moves the university to Partner Activated (OB8) and the page refreshes so the stage panel shows it.
export default function UniversityOnboarding({ universityId, initial }: { universityId: string; initial: OnboardingPage | null }) {
  const router = useRouter();
  const [data, setData] = useState<OnboardingPage | null>(initial);
  const [loadFailed, setLoadFailed] = useState(initial === null);
  // QA27-01: a page refresh (a signing, a course added, this section's own activation) hands a fresh server checklist in; take it
  // without remounting, so a notice just shown stays.
  const [shown, setShown] = useState(initial);
  if (initial !== shown) {
    setShown(initial);
    if (initial !== null) {
      setData(initial);
      setLoadFailed(false);
    }
  }
  const [editing, setEditing] = useState<OnboardingItem | null>(null);
  const [values, setValues] = useState<Values>({ status: "not_started", owner_user_id: "", due_date: "", note: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a second submit before the re-render (double click) sends nothing
  const focus = useFocusAfterRender();
  const id = (part: string) => `onboarding-${universityId}-${part}`;
  const automatic = editing?.completed_by === "auto";

  async function reload() {
    setLoadFailed(false);
    const response = await fetch(onboardingUrl(universityId)).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    if (isOnboardingPage(body)) setData(body);
    else setLoadFailed(true);
  }

  function open(item: OnboardingItem) {
    setEditing(item);
    setValues({ status: item.status, owner_user_id: item.owner?.id ?? "", due_date: item.due_date ?? "", note: item.note ?? "" });
    setErrors({});
    setFailure(null);
    setNotice(null);
    focus(id(item.completed_by === "auto" ? "due_date" : "status"));
  }

  function close() {
    if (editing === null) return;
    const back = id(`edit-${editing.kind}`);
    setEditing(null);
    setErrors({});
    focus(back);
  }

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") close();
  };

  async function save(event: FormEvent) {
    event.preventDefault();
    if (editing === null || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    setErrors({});
    try {
      const body = {
        ...(automatic ? {} : { status: values.status }),
        owner_user_id: values.owner_user_id || null, due_date: values.due_date || null, note: values.note.trim() || null,
      };
      const outcome = await sendJson(onboardingUrl(universityId, editing.kind), "PATCH", body);
      if (!outcome.ok) {
        const fields = fieldErrors(outcome.detail);
        if (Object.keys(fields).length) setErrors(fields);
        else setFailure(conflictMessage(outcome.detail) ?? outcome.message);
        return;
      }
      if (isOnboardingPage(outcome.data)) setData(outcome.data);
      const back = id(`edit-${editing.kind}`);
      setEditing(null);
      focus(back);
      if (outcome.data.stage_advanced === true) {
        setNotice("Onboarding completed: the university is now Partner Activated.");
        router.refresh();
      } else {
        setNotice(`${editing.label} saved.`);
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const describedBy = (key: string) => (errors[key] ? id(`${key}-error`) : undefined);
  const error = (key: string) => errors[key] && <p id={id(`${key}-error`)} className="form-error">{errors[key]}</p>;

  return (
    <section className="action-card wide" aria-labelledby={id("heading")}>
      <h3 id={id("heading")}>Partner onboarding</h3>
      {notice && <p className="form-message" role="status">{notice}</p>}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {loadFailed || data === null ? (
        <div className="actions" style={{ alignItems: "center" }}>
          <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the onboarding checklist.</p>
          <button type="button" className="btn secondary small" onClick={() => void reload()}>Try again</button>
        </div>
      ) : !data.started ? (
        <p className="muted" style={{ margin: 0 }}>Onboarding starts when an agreement is signed.</p>
      ) : (
        <>
          <p style={{ marginTop: 0 }}>
            <span className={STATUS_CLASS[data.status]}>{STATUS_LABEL[data.status]}</span>{" "}
            <span className="muted">
              {data.completed_count} of {data.items.length} completed{data.started_on && ` · Started ${formatCalendarDate(data.started_on)}`}
            </span>
          </p>
          <div className="table-wrap">
            <table className="table milestone-table">{/* QA27-02: the tracker table's phone styling (status pills never wrap) */}
              <caption className="visually-hidden">Partner onboarding checklist</caption>
              <thead>
                <tr>
                  <th scope="col">Item</th><th scope="col">Status</th><th scope="col">Owner</th><th scope="col">Due date</th><th scope="col">Completed</th>
                  <th scope="col">Note</th>{data.can_edit && <th scope="col"><span className="visually-hidden">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.kind}>
                    <th scope="row">{item.label}</th>
                    <td><span className={STATUS_CLASS[item.status]}>{STATUS_LABEL[item.status]}</span></td>
                    <td>{item.owner?.full_name ?? "—"}</td>
                    <td>{item.due_date ? formatCalendarDate(item.due_date) : "—"}</td>
                    <td>
                      {item.completed_by === "auto" ? <span className="muted">Automatic: the university has active courses</span>
                        : item.completed_on ? formatCalendarDate(item.completed_on) : "—"}
                    </td>
                    <td style={{ overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{item.note ?? "—"}</td>
                    {data.can_edit && (
                      <td>
                        <button id={id(`edit-${item.kind}`)} type="button" className="btn ghost small" aria-label={`Edit ${item.label}`} onClick={() => open(item)}
                          disabled={busy || editing !== null}>
                          Edit
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editing && (
            <form className="form-grid" onSubmit={save} onKeyDown={onKeyDown} aria-label={`Edit ${editing.label}`} noValidate style={{ alignItems: "start", marginTop: 12 }}>
              {automatic ? (
                <p className="muted" style={{ margin: 0 }}>Completed automatically while the university has an active course.</p>
              ) : (
                <div className="field">
                  <label htmlFor={id("status")}>Status</label>
                  <select id={id("status")} value={values.status} onChange={(e) => setValues((v) => ({ ...v, status: e.target.value as OnboardingStatus }))}
                    aria-invalid={errors.status ? true : undefined} aria-describedby={describedBy("status")}>
                    {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                  </select>
                  {error("status")}
                </div>
              )}
              <div className="field">
                <SearchableSelect id={id("owner_user_id")} label="Owner" noun="employee" search={signatorySearch} disabled={busy}
                  initial={editing.owner ? { id: editing.owner.id, label: editing.owner.full_name } : null}
                  onChange={(option) => setValues((v) => ({ ...v, owner_user_id: option?.id ?? "" }))} />
                {error("owner_user_id")}
              </div>
              <div className="field">
                <label htmlFor={id("due_date")}>Due date</label>
                <input id={id("due_date")} type="date" value={values.due_date} onChange={(e) => setValues((v) => ({ ...v, due_date: e.target.value }))}
                  aria-invalid={errors.due_date ? true : undefined} aria-describedby={describedBy("due_date")} />
                {error("due_date")}
              </div>
              <div className="field">
                <label htmlFor={id("note")}>Note</label>
                <textarea id={id("note")} rows={2} maxLength={500} value={values.note} onChange={(e) => setValues((v) => ({ ...v, note: e.target.value }))}
                  aria-invalid={errors.note ? true : undefined} aria-describedby={describedBy("note")} />
                {error("note")}
              </div>
              <div className="actions">
                <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
                <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
