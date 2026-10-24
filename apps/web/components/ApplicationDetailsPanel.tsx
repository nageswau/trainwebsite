"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { money } from "@/lib/applicationOffers";
import {
  ApplicationDetails,
  changedFields,
  CURRENCIES,
  DETAIL_FIELDS,
  DetailsForm,
  detailsProblem,
  detailsUrl,
  SCHOLARSHIP_LABELS,
  SCHOLARSHIP_STATUSES,
  scholarshipText,
  toForm,
} from "@/lib/applicationDetails";

type Props = { applicationId: string; onChanged: (message: string) => void };

function shown(details: ApplicationDetails, name: string): ReactNode {
  const value = details[name];
  if (name === "tuition_fee") return value === null ? null : money(details.currency === null ? null : String(details.currency), String(value));
  if (name === "scholarship_status") return scholarshipText(details);
  if (name === "university_portal_url" && value) {
    return (
      <a href={String(value)} target="_blank" rel="noopener noreferrer">
        {String(value)}
      </a>
    );
  }
  return value === null ? null : String(value);
}

// ccrm-013 (DEC-SCOPE-256): an application's university-side fields and its three dates, on the counselor's application card. The
// server checks every rule and the scope again; on an agency application the agency is told (CC5).
export default function ApplicationDetailsPanel({ applicationId, onChanged }: Props) {
  const [details, setDetails] = useState<ApplicationDetails | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<DetailsForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(detailsUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setDetails(outcome.data as unknown as ApplicationDetails);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form || !details || inFlight.current) return;
    const awarded = form.scholarship_status === "awarded";
    const checked = awarded ? form : { ...form, scholarship_amount: "" }; // the server clears the amount when the award goes (F3)
    const problem = detailsProblem(checked);
    if (problem) return setError(problem);
    const body = changedFields(checked, details);
    if (!awarded) delete body.scholarship_amount;
    if (Object.keys(body).length === 0) return setForm(null);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(detailsUrl(applicationId), "PATCH", body);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return setError(outcome.message);
    setDetails(outcome.data as unknown as ApplicationDetails);
    setForm(null);
    onChanged("Application details saved.");
  }

  if (loadError) {
    return (
      <div className="form-error" role="alert" style={{ marginTop: 8 }}>
        {loadError}{" "}
        <button type="button" className="btn ghost small" onClick={load}>
          Try again
        </button>
      </div>
    );
  }
  if (details === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading details…</p>;

  if (form === null) {
    return (
      <section aria-label="Application details" style={{ marginTop: 8 }}>
        <dl className="card-stack" style={{ fontSize: 13 }}>
          {DETAIL_FIELDS.filter(({ name }) => name !== "scholarship_amount" && name !== "currency").map(({ name, label }) => (
            <div key={name}>
              <dt>{label}</dt>
              <dd style={{ overflowWrap: "anywhere" }}>{shown(details, name) ?? "—"}</dd>
            </div>
          ))}
        </dl>
        <button type="button" className="btn small" style={{ marginTop: 8 }} onClick={() => (setForm(toForm(details)), setError(null))}>
          Edit details
        </button>
      </section>
    );
  }

  const set = (name: string, value: string) => setForm({ ...form, [name]: value });
  const id = (name: string) => `${name}-${applicationId}`;
  return (
    <form className="form" onSubmit={submit} aria-label="Edit application details" style={{ marginTop: 8 }} noValidate>
      {DETAIL_FIELDS.map(({ name, label, kind }) => (
        <div className="field" key={name}>
          <label htmlFor={id(name)}>{label}</label>
          {kind === "currency" || kind === "scholarship" ? (
            <select id={id(name)} value={form[name]} onChange={(event) => set(name, event.target.value)}>
              <option value="">{kind === "currency" ? "Choose a currency" : "Not recorded"}</option>
              {(kind === "currency" ? CURRENCIES : SCHOLARSHIP_STATUSES).map((option) => (
                <option key={option} value={option}>
                  {kind === "currency" ? option : SCHOLARSHIP_LABELS[option]}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={id(name)}
              type={kind === "money" ? "number" : kind === "text" ? "text" : kind}
              inputMode={kind === "money" ? "decimal" : undefined}
              min={kind === "money" ? 0 : undefined}
              step={kind === "money" ? "0.01" : undefined}
              maxLength={kind === "url" ? 500 : kind === "email" ? 254 : kind === "text" ? 140 : undefined}
              value={name === "scholarship_amount" && form.scholarship_status !== "awarded" ? "" : form[name]}
              disabled={name === "scholarship_amount" && form.scholarship_status !== "awarded"}
              onChange={(event) => set(name, event.target.value)}
            />
          )}
          {name === "scholarship_amount" && <small className="muted">Only when the scholarship is officially awarded.</small>}
          {name === "university_portal_url" && <small className="muted">The link only -- never a username or password.</small>}
        </div>
      ))}
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save details"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={() => setForm(null)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
