"use client";

import { FormEvent, useEffect, useState } from "react";
import type { CertificateSignatory, SignatoryRole } from "@/lib/certificates";

const URL = "/api/v1/admin/certificate-signatories";
const PREVIEW = "/api/v1/admin/certificates/preview";
const SLOTS: { role: SignatoryRole; label: string }[] = [
  { role: "founder", label: "Founder" },
  { role: "coordinator", label: "Coordinator" },
];

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

// nehn-032 (DEC-SCOPE-301): the Founder and Coordinator signatures drawn on every new certificate. A new image is always a new version
// (certificates already issued keep the one they were signed with); without an image, saving edits the current version's details.
export default function AdminCertificateSignaturesPanel() {
  const [items, setItems] = useState<CertificateSignatory[] | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    fetch(URL)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(detailMessage(data.detail, "The certificate signatures could not be loaded."));
        setItems(data.items);
      })
      .catch((error: Error) => setLoadError(error.message || "The certificate signatures could not be loaded."));
  }, []);

  // A saved version is its slot's active one: an upload closes the previous version, an edit replaces the same row.
  const saved = (item: CertificateSignatory) =>
    setItems((current) => [item, ...(current ?? []).filter((row) => row.id !== item.id).map((row) => (row.role === item.role ? { ...row, active: false } : row))]);

  return (
    <div className="action-card">
      <h3>Certificate signatures</h3>
      <p className="muted">Every new certificate carries both signatures with the signer&apos;s name and designation. Upload a PNG with a transparent background (at most 1 MB, 50–2000 px wide). Certificates already issued keep the signature they were issued with.</p>
      {!items && !loadError && <p className="muted">Loading the certificate signatures…</p>}
      {loadError && <div className="form-error" role="alert">{loadError}</div>}
      {items && (
        <>
          {SLOTS.map((slot) => (
            <SignatureSlot key={slot.role} {...slot} current={items.find((item) => item.role === slot.role && item.active) ?? null} onSaved={saved} />
          ))}
          {/* QA32-01: the preview needs both slots (the API answers 409 otherwise), so say so instead of linking to an error */}
          {SLOTS.every((slot) => items.some((item) => item.role === slot.role && item.active)) ? (
            <a className="btn ghost small" href={PREVIEW} target="_blank" rel="noopener noreferrer">Preview certificate (opens a PDF)</a>
          ) : (
            <p className="muted">Upload both signatures to preview the certificate.</p>
          )}
        </>
      )}
    </div>
  );
}

function SignatureSlot({ role, label, current, onSaved }: { role: SignatoryRole; label: string; current: CertificateSignatory | null; onSaved: (item: CertificateSignatory) => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = (formElement.elements.namedItem("file") as HTMLInputElement).files?.[0];
    const details = { display_name: String(form.get("display_name") ?? ""), designation: String(form.get("designation") ?? "") };
    let request: RequestInit;
    if (file) {
      const body = new FormData();
      body.append("role", role);
      body.append("display_name", details.display_name);
      body.append("designation", details.designation);
      body.append("file", file);
      request = { method: "POST", body };
    } else {
      request = { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(details) };
    }
    setBusy(true);
    setMessage("");
    setFailed(false);
    const response = await fetch(file ? URL : `${URL}/${current?.id}`, request).catch(() => null);
    const data = await response?.json().catch(() => ({}));
    setBusy(false);
    if (!response?.ok) {
      setFailed(true);
      setMessage(detailMessage(data?.detail, `The ${label.toLowerCase()} signature could not be saved.`));
      return;
    }
    formElement.reset();
    onSaved(data);
    setMessage(`${label} signature saved. It applies to certificates issued from now on.`);
  }

  const id = `signature-${role}`;
  return (
    <fieldset className="field signature-slot" aria-label={`${label} signature`}>
      <legend><strong>{label} signature</strong></legend>
      {current ? (
        <div className="signature-current">
          {/* eslint-disable-next-line @next/next/no-img-element -- a private, session-checked API image; next/image cannot proxy it */}
          <img src={`${URL}/${current.id}/image`} alt={`${current.display_name} signature`} />
          <div>
            <strong>{current.display_name}</strong>
            <div className="muted">{current.designation}</div>
          </div>
        </div>
      ) : (
        <p className="muted">No signature uploaded. Certificates cannot be issued until both signatures are uploaded.</p>
      )}
      <form className="form" onSubmit={save} key={current?.id ?? "empty"}>
        <div className="field">
          <label htmlFor={`${id}-name`}>Name</label>
          <input id={`${id}-name`} name="display_name" required maxLength={120} defaultValue={current?.display_name ?? ""} />
        </div>
        <div className="field">
          <label htmlFor={`${id}-designation`}>Designation</label>
          <input id={`${id}-designation`} name="designation" required maxLength={120} defaultValue={current?.designation ?? ""} />
        </div>
        <div className="field">
          <label htmlFor={`${id}-file`}>Signature image (PNG){current ? " — leave empty to keep the current one" : ""}</label>
          <input id={`${id}-file`} name="file" type="file" accept="image/png" required={!current} />
        </div>
        <button className="btn small" disabled={busy} aria-label={`Save ${label.toLowerCase()} signature`}>{busy ? "Saving…" : "Save signature"}</button>
      </form>
      {message && <div className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live="polite">{message}</div>}
    </fieldset>
  );
}
