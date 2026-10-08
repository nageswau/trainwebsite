"use client";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import BdmConfirm from "@/components/BdmConfirm";
import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { display } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { fileSize } from "@/lib/recruiterCandidates";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";
import {
  isJd,
  type Jd,
  JD_ACCEPT,
  JD_FIELDS,
  JD_LABEL,
  JD_MAX_BYTES,
  JD_MULTILINE,
  jdBody,
  jdFileUrl,
  jdUrl,
  jdValues,
  type JdValues,
  type JdVersion,
  requirementChangesFromJd,
} from "@/lib/recruiterJd";
import { isRequirementBody, type Requirement, REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-008 (DEC-SCOPE-132, spec §4): the requirement's JD -- the current version, create/edit (a new version), upload (a new version),
// the version list with downloads, and JD6's confirmed copy onto the requirement. Every write re-renders from what the API returns.
type Notice = { text: string; failed: boolean } | null;
type Props = { requirement: Requirement; initial: Jd | null; onRequirementChanged: (next: Requirement, notice: string) => void };
type ContactOption = { id: string; name: string };

function JdForm({ requirement, current, onSaved, onCancel }: { requirement: Requirement; current?: JdVersion; onSaved: (jd: Jd) => void; onCancel: () => void }) {
  const [values, setValues] = useState<JdValues>(() => jdValues(current, requirement));
  const [contacts, setContacts] = useState<ContactOption[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `requirement-${requirement.id}-jd-form`;

  useEffect(() => {
    const controller = new AbortController();
    fetch(contactsOf(requirement.company.id), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setContacts(isContactList(data) ? data.items.filter((c) => c.active).map((c) => ({ id: c.id, name: c.name })) : []))
      .catch(() => controller.signal.aborted || setContacts([]));
    return () => controller.abort();
  }, [requirement.company.id]);

  // The current contact stays choosable even if since deactivated (the API keeps it; JD3).
  const options = [...(contacts ?? [])];
  if (current?.contact && !options.some((c) => c.id === current.contact!.id)) options.unshift({ id: current.contact.id, name: `${current.contact.name}${current.contact.active ? "" : " (inactive)"}` });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(jdUrl(requirement.id), "POST", jdBody(values));
    setBusy(false);
    if (outcome.ok && isJd(outcome.data)) onSaved(outcome.data);
    else setFailure(outcome.ok ? "Unable to save the JD." : outcome.message);
  }

  const input = (key: (typeof JD_FIELDS)[number]): ReactNode => {
    const common = { id: `${id}-${key}`, value: values[key], disabled: busy, onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [key]: e.target.value })) };
    if (key === "contact_id") {
      return (
        <select {...common}>
          <option value="">{contacts === null ? "Loading contacts…" : "No contact person"}</option>
          {options.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      );
    }
    if (JD_MULTILINE.has(key)) return <textarea {...common} rows={key === "skills" ? 2 : 4} />;
    if (key === "closing_date") return <input {...common} type="date" />;
    if (key === "openings") return <input {...common} type="number" min={1} max={10000} inputMode="numeric" />;
    return <input {...common} type="text" required={key === "role"} />;
  };

  return (
    <form className="form" onSubmit={submit} aria-busy={busy} aria-labelledby={`${id}-title`}>
      <h4 id={`${id}-title`} style={{ margin: 0 }}>{current ? `Edit JD (saves version ${current.version + 1})` : "Create JD"}</h4>
      <div className="form-grid">
        {JD_FIELDS.map((key) => (
          <div key={key} className={JD_MULTILINE.has(key) ? "field wide" : "field"} style={JD_MULTILINE.has(key) ? { gridColumn: "1 / -1" } : undefined}>
            <label htmlFor={`${id}-${key}`}>
              {JD_LABEL[key]}
              {key === "role" ? " *" : ""}
            </label>
            {input(key)}
          </div>
        ))}
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save JD"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function JdUpload({ requirementId, hasJd, onUploaded }: { requirementId: string; hasJd: boolean; onUploaded: (jd: Jd, notice: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `requirement-${requirementId}-jd-file`;

  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return setFailure("Choose a PDF or DOCX file first.");
    if (file.size > JD_MAX_BYTES) return setFailure("The JD file must be at most 5 MB.");
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const form = new FormData();
    form.append("file", file);
    const outcome = await sendRequest(`${jdUrl(requirementId)}/file`, { method: "PUT", body: form });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok || !isJd(outcome.data)) return setFailure(outcome.ok ? "Unable to upload the JD." : outcome.message);
    if (input.current) input.current.value = "";
    onUploaded(outcome.data, `JD file uploaded as version ${outcome.data.versions[0].version}.`);
  }

  return (
    <form onSubmit={upload} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
      <div className="field" style={{ flex: "1 1 16rem", marginBottom: 0 }}>
        <label htmlFor={id}>{hasJd ? "Upload a new JD file (new version)" : "Upload JD"}</label>
        <span id={`${id}-hint`} className="muted" style={{ fontSize: 13 }}>
          PDF or DOCX, up to 5 MB. It is linked to this requirement automatically.
        </span>
        <input id={id} ref={input} type="file" accept={JD_ACCEPT} aria-describedby={`${id}-hint`} disabled={busy} />
      </div>
      <button type="submit" className="btn secondary small" disabled={busy}>
        {busy ? "Uploading…" : "Upload"}
      </button>
      {failure && (
        <p className="form-error" role="alert" style={{ flexBasis: "100%", margin: 0 }}>
          {failure}
        </p>
      )}
    </form>
  );
}

function ApplyToRequirement({ requirement, current, onApplied }: { requirement: Requirement; current: JdVersion; onApplied: (next: Requirement) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const { changes, patch } = requirementChangesFromJd(current, requirement);
  const triggerId = `requirement-${requirement.id}-jd-apply`;
  if (changes.length === 0) return <p className="muted" style={{ margin: 0 }}>The requirement already matches this JD.</p>;

  async function apply() {
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${REQUIREMENTS_URL}/${requirement.id}`, "PATCH", patch);
    setBusy(false);
    setConfirming(false);
    if (outcome.ok && isRequirementBody(outcome.data)) onApplied(outcome.data.requirement);
    else setFailure(outcome.ok ? "Unable to update the requirement." : outcome.message);
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {!confirming && (
        <div>
          <button id={triggerId} type="button" className="btn secondary small" onClick={() => setConfirming(true)}>
            Update requirement from JD
          </button>
        </div>
      )}
      {confirming && (
        <BdmConfirm
          label="Confirm requirement update"
          confirmText="Yes, update requirement"
          busyText="Updating…"
          busy={busy}
          onConfirm={() => void apply()}
          onCancel={() => {
            setConfirming(false);
            focus(triggerId);
          }}
        >
          Copy these JD values onto {requirement.code}?
        </BdmConfirm>
      )}
      {confirming && (
        <ul style={{ margin: 0, paddingLeft: 18 }} aria-label="Changes">
          {changes.map((c) => (
            <li key={c.label} style={{ overflowWrap: "anywhere" }}>
              <strong>{c.label}:</strong> {c.from.length > 80 ? `${c.from.slice(0, 80)}…` : c.from} → {c.to.length > 80 ? `${c.to.slice(0, 80)}…` : c.to}
            </li>
          ))}
        </ul>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </div>
  );
}

export default function RecruiterRequirementJd({ requirement, initial, onRequirementChanged }: Props) {
  const [jd, setJd] = useState<Jd | null>(initial);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const focus = useFocusAfterRender();
  const r = requirement;
  const headingId = `requirement-${r.id}-jd`;
  const noticeId = `${headingId}-notice`;
  const editId = `${headingId}-edit`;
  const current = jd?.versions[0];

  const saved = (next: Jd, text: string) => {
    setJd(next);
    setEditing(false);
    setNotice({ text, failed: false });
    focus(noticeId);
  };

  const rows: [string, ReactNode][] = current
    ? [
        ["JD number", `${jd!.jd_number} · version ${current.version}`],
        ["Company", `${r.company.name} (${r.company.code})`],
        ["Job role", current.role],
        ["Experience", display(current.experience)],
        ["Qualification", display(current.qualification)],
        ["Skills", multiline(current.skills)],
        ["Salary", display(current.salary)],
        ["Location", display(current.location)],
        ["Job description", multiline(current.description)],
        ["Responsibilities", multiline(current.responsibilities)],
        ["Requirements", multiline(current.requirements)],
        ["Number of openings", current.openings == null ? "—" : String(current.openings)],
        ["Contact person", current.contact ? `${current.contact.name}${current.contact.active ? "" : " (inactive)"}` : "—"],
        ["Closing date", current.closing_date ? formatCalendarDate(current.closing_date) : "—"],
        [
          "JD file",
          current.file ? (
            <a href={jdFileUrl(r.id, current.version)} download style={{ overflowWrap: "anywhere" }}>
              {current.file.name ?? "Download"} ({fileSize(current.file.size_bytes)})
            </a>
          ) : (
            "No file — created in the form"
          ),
        ],
        ["Saved by", current.created_by ? <>{current.created_by.full_name} on <LocalTime value={current.created_at} time /></> : <LocalTime value={current.created_at} time />],
      ]
    : [];

  return (
    <section className="action-card wide" aria-labelledby={headingId} style={{ display: "grid", gap: 12 }}>
      <h3 id={headingId} style={{ margin: 0 }}>
        Job description (JD) {jd?.jd_number && <span className="badge">{jd.jd_number}</span>}
      </h3>
      <div id={noticeId} tabIndex={-1} role="status" aria-live="polite" className={notice && !notice.failed ? "form-message" : undefined}>
        {notice?.text}
      </div>
      {jd === null ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          The JD could not be loaded. Refresh the page to try again.
        </p>
      ) : (
        <>
          {!current && <p className="muted" style={{ margin: 0 }}>No JD yet.{jd.can_edit ? " Create one from this requirement or upload a PDF/DOCX file." : ""}</p>}
          {current?.closing_date_differs && (
            <p className="status pending" role="note" style={{ margin: 0, display: "inline-block" }}>
              The JD closing date ({formatCalendarDate(current.closing_date!)}) differs from the requirement&apos;s application deadline (
              {r.closes_on ? formatCalendarDate(r.closes_on) : "not set"}).
            </p>
          )}
          {current && !editing && <DetailList rows={rows} />}
          {editing && jd.can_edit ? (
            <JdForm
              requirement={r}
              current={current}
              onSaved={(next) => saved(next, `JD saved as version ${next.versions[0].version}.`)}
              onCancel={() => {
                setEditing(false);
                focus(editId);
              }}
            />
          ) : (
            jd.can_edit && (
              <div className="actions">
                <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
                  {current ? "Edit JD" : "Create JD"}
                </button>
              </div>
            )
          )}
          {jd.can_edit && !editing && <JdUpload requirementId={r.id} hasJd={!!current} onUploaded={saved} />}
          {current && r.permissions.can_edit && !editing && (
            <ApplyToRequirement
              requirement={r}
              current={current}
              onApplied={(next) => {
                onRequirementChanged(next, "Requirement updated from the JD.");
              }}
            />
          )}
          {jd.versions.length > 1 && (
            <div>
              <h4 style={{ margin: "0 0 4px" }}>Versions</h4>
              <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 6 }}>
                {jd.versions.map((v) => (
                  <li key={v.version} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                    <span style={{ fontWeight: v.is_current ? 600 : undefined }}>Version {v.version}</span>
                    {v.is_current && <span className="badge">Current</span>}
                    {v.file ? (
                      <a href={jdFileUrl(r.id, v.version)} download style={{ overflowWrap: "anywhere" }}>
                        {v.file.name ?? "Download file"}
                      </a>
                    ) : (
                      <span className="muted">form only</span>
                    )}
                    <span className="muted" style={{ fontSize: 13 }}>
                      <LocalTime value={v.created_at} time />
                      {v.created_by ? ` · ${v.created_by.full_name}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
