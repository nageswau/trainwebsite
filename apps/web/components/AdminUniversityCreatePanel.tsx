"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Country } from "@/lib/types";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to create university.";
}

// RAID.md I-32 (Tier 0 of the reference-dropdown audit) -- "Country slug" used to be a
// bare typed text field on this form; an admin had to already know the exact slug by
// heart, and a typo produced a plain 422 "Unknown country" with no hint what a valid
// value looks like. Replaces it with a real picker sourced from the same public country
// catalogue OVS-001 already exposes -- same "list real options instead of typing a raw
// reference" precedent as AdminBatchCreatePanel (ADM-003) and OverseasApplyPanel (OVS-002).
// `slug`/`name`/etc. stay free text below -- those define the *new* university being
// created, not a reference to an existing one.
export default function AdminUniversityCreatePanel() {
  const router = useRouter();
  const [countries, setCountries] = useState<Country[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/countries")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: Country[]) => !cancelled && setCountries(data))
      .catch(() => !cancelled && setCountries([]));
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
    const response = await fetch("/api/v1/admin/universities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country_slug: form.get("country_slug"),
        slug: form.get("slug"),
        name: form.get("name"),
        city: form.get("city") || "",
        overview: form.get("overview") || "",
        eligibility: form.get("eligibility") || "",
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "University created.", failed: false });
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Create university</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="university-country">Country</label>
          <select id="university-country" name="country_slug" required disabled={!countries.length}>
            <option value="">{countries.length ? "Select country" : "Loading countries…"}</option>
            {countries.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="university-slug">University slug</label>
          <input id="university-slug" name="slug" required placeholder="e.g. university-of-oxford" />
        </div>
        <div className="field">
          <label htmlFor="university-name">University name</label>
          <input id="university-name" name="name" required />
        </div>
        <div className="field">
          <label htmlFor="university-city">City</label>
          <input id="university-city" name="city" />
        </div>
        <div className="field full">
          <label htmlFor="university-overview">Overview</label>
          <textarea id="university-overview" name="overview" />
        </div>
        <div className="field full">
          <label htmlFor="university-eligibility">Eligibility</label>
          <textarea id="university-eligibility" name="eligibility" />
        </div>
        <button className="btn" disabled={busy || !countries.length}>
          {busy ? "Creating…" : "Create university"}
        </button>
        {!countries.length && <p className="muted" style={{ fontSize: 13 }}>Loading the country catalogue…</p>}
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
