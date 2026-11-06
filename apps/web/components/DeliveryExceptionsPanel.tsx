"use client";
import Link from "next/link";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { CHANNELS, channelLabel, EXCEPTIONS_PATH, type ExceptionFilters, type ExceptionPage, type ExceptionRow, PAGE_SIZE, pageHref, retryUrl } from "@/lib/notificationExceptions";

// hrc-032 (DEC-SCOPE-413 N8/N9): recruitment deliveries that failed, each with its error, attempts and a Retry. A row that left the failed state
// leaves the list (the API's answer is the truth); it comes back if the retry fails again. The filters are a plain GET form, so a filtered
// list has a URL.
function Row({ row, onGone }: { row: ExceptionRow; onGone: (text: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const title = `exception-${row.id}-title`;

  async function retry() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(retryUrl(row), "POST", {});
    setBusy(false);
    if (outcome.ok) onGone(`Retry queued for ${row.recipient}. If it fails again, it comes back to this list.`);
    else if (outcome.status === 409) onGone(`The ${row.type_label} notice for ${row.recipient} is no longer failed.`);
    else setError(outcome.message);
  }

  return (
    <li className="action-card" style={{ margin: 0, overflowWrap: "anywhere" }} aria-labelledby={title}>
      <div className="eyebrow">{row.type_label} · {channelLabel(row.channel)}</div>
      <h4 id={title} style={{ margin: "4px 0" }}>{row.recipient}</h4>
      <p style={{ margin: 0 }}>{row.error ?? "The email could not be sent."}</p>
      <p className="muted" style={{ margin: "4px 0 8px", fontSize: 13 }}>Attempts: {row.attempts} · Failed on {formatSchoolDateTime(row.failed_at)}</p>
      {error && <p className="form-error" role="alert" style={{ margin: "0 0 8px" }}>{error}</p>}
      <div>
        <button type="button" className="btn small" disabled={busy} onClick={() => void retry()} aria-label={`Retry ${row.type_label} for ${row.recipient}`}>
          {busy ? "Retrying…" : "Retry"}
        </button>
      </div>
    </li>
  );
}

export default function DeliveryExceptionsPanel({ page, filters }: { page: ExceptionPage; filters: ExceptionFilters }) {
  const [rows, setRows] = useState(page.items);
  const [notice, setNotice] = useState<string | null>(null);
  const filtered = Boolean(filters.type || filters.channel);
  const remaining = page.total - (page.items.length - rows.length);

  return (
    <>
      <form className="form filter-bar" action={EXCEPTIONS_PATH} method="get" aria-label="Filter failed deliveries" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
        <div className="field">
          <label htmlFor="exception-type">Type</label>
          <select id="exception-type" name="type" defaultValue={filters.type}>
            <option value="">All types</option>
            {page.types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="exception-channel">Channel</label>
          <select id="exception-channel" name="channel" defaultValue={filters.channel}>
            <option value="">All channels</option>
            {CHANNELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
        <button type="submit" className="btn small">Apply filters</button>
        {filtered && <Link className="btn small secondary" href={EXCEPTIONS_PATH}>Clear filters</Link>}
      </form>
      <div id="exception-notice" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      <section className="action-card wide" aria-labelledby="exception-list">
        <h3 id="exception-list">Failed deliveries ({remaining})</h3>
        {rows.length === 0 ? (
          <p style={{ margin: 0 }}>{filtered ? "No failed deliveries match these filters." : "No failed deliveries. Everything sent has been delivered or is still being tried."}</p>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>A retry sends the message as it was first written, and starts a new round of automatic attempts.</p>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 16 }}>
              {rows.map((row) => (
                <Row key={`${row.source}-${row.id}`} row={row} onGone={(text) => {
                  setRows((current) => current.filter((r) => r.id !== row.id));
                  setNotice(text);
                  document.getElementById("exception-notice")?.focus();
                }} />
              ))}
            </ul>
          </>
        )}
        {page.total > page.items.length && (
          <nav aria-label="Pages" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
            <span className="muted">Showing {page.offset + 1}–{page.offset + page.items.length} of {page.total}.</span>
            {page.offset > 0 && <Link className="btn small secondary" href={pageHref({ ...filters, offset: Math.max(0, page.offset - PAGE_SIZE) })}>Previous page</Link>}
            {page.offset + page.items.length < page.total && <Link className="btn small secondary" href={pageHref({ ...filters, offset: page.offset + PAGE_SIZE })}>Next page</Link>}
          </nav>
        )}
      </section>
    </>
  );
}
