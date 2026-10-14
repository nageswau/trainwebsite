"use client";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  CONSENT_TEXT,
  type Division,
  draftBody,
  draftFrom,
  emptyDraft,
  MANAGE_URL,
  type ManagedTestimonial,
  photoUrl,
  type TestimonialDraft,
  TESTIMONIALS_URL,
  testimonialUrl,
} from "@/lib/testimonials";

// PUB-022 (DEC-SCOPE-210): manage homepage testimonials. Publishing needs the consent tick (SP6); unticking consent also
// unpublishes (SP9); delete is permanent and asks first. `divisions` is both for a Super Admin, the admin's own otherwise (SP2).
export default function TestimonialManager({ divisions }: { divisions: Division[] }) {
  const listUrl = divisions.length === 1 ? `${MANAGE_URL}?division=${divisions[0]}` : MANAGE_URL;
  const [rows, setRows] = useState<ManagedTestimonial[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ManagedTestimonial | "new" | null>(null);
  const [draft, setDraft] = useState<TestimonialDraft>(emptyDraft(divisions[0]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [uploads, setUploads] = useState(0); // re-keys the file input so it empties after each upload / row switch

  const load = useCallback(async () => {
    try {
      const response = await fetch(listUrl);
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      setRows(Array.isArray(data) ? data : []);
      setLoadError(null);
    } catch {
      setLoadError("Could not load testimonials. Refresh the page to try again.");
    }
  }, [listUrl]);

  useEffect(() => {
    void load();
  }, [load]);

  function begin() {
    setError(null);
    setNotice(null);
  }

  function open(target: ManagedTestimonial | "new") {
    if (busy) return;
    setEditing(target);
    setDraft(target === "new" ? emptyDraft(divisions[0]) : draftFrom(target));
    setError(null);
    setNotice(null);
    setPhoto(null);
    setUploads((n) => n + 1);
  }

  function set<K extends keyof TestimonialDraft>(key: K, value: TestimonialDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value, ...(key === "consent_confirmed" && !value ? { published: false } : {}) }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || editing === null) return;
    begin();
    if (!draft.person_name.trim() || !draft.headline.trim() || !draft.quote.trim()) return setError("Enter the name, headline and quote.");
    setBusy(true);
    const creating = editing === "new";
    const outcome = await sendJson(creating ? TESTIMONIALS_URL : testimonialUrl(editing.id), creating ? "POST" : "PATCH", draftBody(draft, creating));
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setNotice(creating ? "Testimonial added." : "Testimonial saved.");
    await load();
    const saved = outcome.data as unknown as ManagedTestimonial;
    setEditing(saved);
    setDraft(draftFrom(saved));
  }

  async function uploadPhoto() {
    if (busy || !editing || editing === "new" || !photo) return;
    const form = new FormData();
    form.append("file", photo);
    begin();
    setBusy(true);
    const outcome = await sendRequest(photoUrl(editing.id), { method: "PUT", body: form });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setNotice("Photo uploaded.");
    setPhoto(null);
    setUploads((n) => n + 1);
    setEditing(outcome.data as unknown as ManagedTestimonial);
    await load();
  }

  async function removePhoto() {
    if (busy || !editing || editing === "new") return;
    begin();
    setBusy(true);
    const outcome = await sendRequest(photoUrl(editing.id), { method: "DELETE" });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setNotice("Photo removed.");
    setEditing(outcome.data as unknown as ManagedTestimonial);
    await load();
  }

  async function remove() {
    if (busy || !editing || editing === "new") return;
    if (!window.confirm(`Delete the testimonial from ${editing.person_name} permanently? Their name, words and photo are removed and cannot be restored.`)) return;
    begin();
    setBusy(true);
    let ok = false;
    try {
      ok = (await fetch(testimonialUrl(editing.id), { method: "DELETE" })).status === 204;
    } catch {
      ok = false;
    }
    setBusy(false);
    if (!ok) return setError("The testimonial was not deleted. Try again.");
    setEditing(null);
    setNotice("Testimonial deleted.");
    await load();
  }

  const current = editing && editing !== "new" ? editing : null;
  return (
    <section className="action-card" aria-labelledby="testimonials-title" style={{ gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <h3 id="testimonials-title">Testimonials</h3>
        <button className="btn small" type="button" disabled={busy} onClick={() => open("new")}>Add testimonial</button>
      </div>
      {notice && <p role="status" className="form-message" style={{ margin: 0 }}>{notice}</p>}
      {loadError && <p role="alert" className="form-error" style={{ margin: 0 }}>{loadError}</p>}
      {rows && rows.length === 0 && <p className="muted" style={{ margin: 0 }}>No testimonials yet.</p>}
      {rows && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Division</th><th>Headline</th><th>Consent</th><th>Published</th><th>Homepage</th><th>Order</th><th><span className="visually-hidden">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td>{t.person_name}</td>
                  <td>{t.division === "it" ? "IT" : "Overseas"}</td>
                  <td>{t.headline}</td>
                  <td>{t.consent_confirmed ? "Yes" : "No"}</td>
                  <td>{t.published ? "Yes" : "No"}</td>
                  <td>{t.featured ? "Featured" : "-"}</td>
                  <td>{t.display_order}</td>
                  <td><button className="btn ghost small" type="button" disabled={busy} onClick={() => open(t)}>Edit<span className="visually-hidden"> {t.person_name}</span></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing !== null && (
        <form onSubmit={save} noValidate aria-label={current ? `Edit testimonial from ${current.person_name}` : "New testimonial"} aria-busy={busy} className="form">
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 14 }}>
            <h4 style={{ margin: 0 }}>{current ? `Edit: ${current.person_name}` : "New testimonial"}</h4>
            <div className="form-grid">
              {editing === "new" && divisions.length > 1 && (
                <div className="field">
                  <label htmlFor="t-division">Division</label>
                  <select id="t-division" value={draft.division} onChange={(e) => set("division", e.target.value as Division)}>
                    {divisions.map((d) => <option key={d} value={d}>{d === "it" ? "IT Training" : "Overseas Education"}</option>)}
                  </select>
                </div>
              )}
              <div className="field">
                <label htmlFor="t-name">Name</label>
                <input id="t-name" maxLength={160} value={draft.person_name} onChange={(e) => set("person_name", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="t-headline">Headline</label>
                <input id="t-headline" maxLength={200} value={draft.headline} onChange={(e) => set("headline", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="t-context">Course / university (optional)</label>
                <input id="t-context" maxLength={160} placeholder="e.g. MSc Data Science · University of Reading" value={draft.context} onChange={(e) => set("context", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="t-rating">Star rating</label>
                <select id="t-rating" value={draft.rating} onChange={(e) => set("rating", Number(e.target.value))}>
                  {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="t-order">Homepage order (lower shows first)</label>
                <input id="t-order" type="number" step={1} value={draft.display_order} onChange={(e) => set("display_order", e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="t-quote">Quote</label>
              <textarea id="t-quote" maxLength={2000} value={draft.quote} onChange={(e) => set("quote", e.target.value)} />
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input type="checkbox" checked={draft.consent_confirmed} onChange={(e) => set("consent_confirmed", e.target.checked)} />
              <span>{CONSENT_TEXT}</span>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={draft.published} disabled={!draft.consent_confirmed} aria-describedby={draft.consent_confirmed ? undefined : "t-publish-help"} onChange={(e) => set("published", e.target.checked)} />
              <span>Publish testimonial</span>
            </label>
            {!draft.consent_confirmed && <p id="t-publish-help" className="muted" style={{ margin: 0 }}>Record consent before publishing.</p>}
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={draft.featured} onChange={(e) => set("featured", e.target.checked)} />
              <span>Show on homepage (up to 6 featured)</span>
            </label>
            {error && <p role="alert" className="form-error" style={{ margin: 0 }}>{error}</p>}
            <div className="actions">
              <button className="btn small" type="submit">{current ? "Save testimonial" : "Add testimonial"}</button>
              <button className="btn ghost small" type="button" onClick={() => setEditing(null)}>Close</button>
              {current && <button className="btn ghost small" type="button" onClick={remove}>Delete permanently</button>}
            </div>
            {current && (
              <div className="field">
                <label htmlFor="t-photo">Photo (JPEG or PNG, up to 2 MB){current.has_photo ? " — a photo is saved" : ""}</label>
                <input key={uploads} id="t-photo" type="file" accept="image/jpeg,image/png" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
                <div className="actions">
                  <button className="btn secondary small" type="button" disabled={!photo} onClick={uploadPhoto}>Upload photo</button>
                  {current.has_photo && <button className="btn ghost small" type="button" onClick={removePhoto}>Remove photo</button>}
                </div>
              </div>
            )}
          </fieldset>
        </form>
      )}
    </section>
  );
}
