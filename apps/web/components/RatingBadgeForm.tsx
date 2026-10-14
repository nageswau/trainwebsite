"use client";
import { type FormEvent, useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { BADGE_URL, badgeBody, type BadgeDraft, badgeDraftFrom } from "@/lib/testimonials";

// PUB-022 SP5: the one organisation-wide rating badge (e.g. "4.8 on Google"), Super Admin only. Shown on the homepage only when published.
export default function RatingBadgeForm() {
  const [draft, setDraft] = useState<BadgeDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch(BADGE_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => live && setDraft(badgeDraftFrom(data)))
      .catch(() => live && setError("Could not load the rating badge. Refresh the page to try again."));
    return () => {
      live = false;
    };
  }, []);

  function set<K extends keyof BadgeDraft>(key: K, value: BadgeDraft[K]) {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !draft) return;
    setError(null);
    setNotice(null);
    if (!draft.source_name.trim() || draft.rating === "" || draft.review_count === "" || !draft.as_of) return setError("Enter the source, rating, review count and date.");
    setBusy(true);
    const outcome = await sendJson(BADGE_URL, "PUT", badgeBody(draft));
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setNotice("Rating badge saved.");
  }

  return (
    <section className="action-card" aria-labelledby="badge-title" style={{ gridColumn: "1 / -1" }}>
      <h3 id="badge-title">Rating badge</h3>
      <p className="muted" style={{ margin: 0 }}>Copy the figures from the review site exactly. The badge shows on the homepage only when published.</p>
      {notice && <p role="status" className="form-message" style={{ margin: 0 }}>{notice}</p>}
      {error && <p role="alert" className="form-error" style={{ margin: 0 }}>{error}</p>}
      {draft && (
        <form onSubmit={save} noValidate aria-label="Rating badge" aria-busy={busy} className="form">
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 14 }}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="b-source">Review site</label>
                <input id="b-source" maxLength={60} value={draft.source_name} onChange={(e) => set("source_name", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="b-rating">Rating (0.0 to 5.0)</label>
                <input id="b-rating" type="number" inputMode="decimal" min={0} max={5} step={0.1} value={draft.rating} onChange={(e) => set("rating", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="b-count">Number of reviews</label>
                <input id="b-count" type="number" inputMode="numeric" min={0} step={1} value={draft.review_count} onChange={(e) => set("review_count", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="b-asof">As of</label>
                <input id="b-asof" type="date" value={draft.as_of} onChange={(e) => set("as_of", e.target.value)} />
              </div>
              <div className="field full">
                <label htmlFor="b-url">Reviews page link (https, optional)</label>
                <input id="b-url" type="url" maxLength={500} placeholder="https://" value={draft.review_url} onChange={(e) => set("review_url", e.target.value)} />
              </div>
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={draft.published} onChange={(e) => set("published", e.target.checked)} />
              <span>Publish rating badge</span>
            </label>
            <div className="actions">
              <button className="btn small" type="submit">Save rating badge</button>
            </div>
          </fieldset>
        </form>
      )}
    </section>
  );
}
