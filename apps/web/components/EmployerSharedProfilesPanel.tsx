"use client";
import { useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import {
  employerItemUrl,
  employerSharesUrl,
  experienceLabel,
  isPortalItem,
  isPortalPage,
  PAGE_SIZE,
  type PortalItem,
  type PortalPage,
  RESPONSES,
  type ShareResponse,
} from "@/lib/recruiterShares";

type Notice = { text: string; failed: boolean } | null;

function Profile({ item, onAnswered }: { item: PortalItem; onAnswered: (next: PortalItem | null, text: string) => void }) {
  const [response, setResponse] = useState<ShareResponse>(item.response);
  const [busy, setBusy] = useState(false);
  const id = useId();
  const c = item.candidate;
  const facts: [string, string | null][] = [
    ["Qualification", [c.qualification, c.college, c.passing_year].filter(Boolean).join(" · ") || null],
    ["Experience", experienceLabel(c.experience_months)],
    ["Current company", c.current_company],
    ["Location", c.location],
    ["Preferred locations", c.preferred_locations.join(", ") || null],
    ["Preferred role", c.preferred_role],
    ["Notice period", c.notice_days === null ? null : `${c.notice_days} days`],
  ];

  async function save() {
    setBusy(true);
    const outcome = await sendJson(employerItemUrl(item.id), "PATCH", { response });
    setBusy(false);
    if (outcome.ok && isPortalItem(outcome.data)) onAnswered(outcome.data, `Response saved for ${c.name}.`);
    else onAnswered(null, outcome.ok ? "Unable to save the response." : outcome.message);
  }

  return (
    <li className="action-card" style={{ listStyle: "none", gap: 8 }} aria-labelledby={`${id}-name`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <h4 id={`${id}-name`} style={{ margin: 0, overflowWrap: "anywhere" }}>{c.name}</h4>
        <span className="muted" style={{ fontSize: 13 }}>{c.code}</span>
        <span className="badge">{item.response_label}</span>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        For {item.requirement.title} ({item.requirement.code}) · shared <LocalTime value={item.shared_at} />
      </p>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))", gap: "6px 12px", margin: 0 }}>
        {facts.filter(([, v]) => v).map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {c.skills.length > 0 && <p style={{ margin: 0, fontSize: 14 }}><span className="muted">Skills:</span> {c.skills.join(", ")}</p>}
      <div className="actions" style={{ flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        {item.has_resume ? (
          <a className="btn secondary small" href={`${employerItemUrl(item.id)}/resume`}>Download resume<span className="visually-hidden"> of {c.name}</span></a>
        ) : <span className="muted" style={{ fontSize: 13 }}>Resume on request</span>}
        <label htmlFor={`${id}-response`} style={{ display: "grid", gap: 4 }}>
          Your response
          <select id={`${id}-response`} value={response} onChange={(e) => setResponse(e.target.value as ShareResponse)}>
            {RESPONSES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        </label>
        <button type="button" className="btn small" disabled={busy || response === item.response} onClick={() => void save()}>
          {busy ? "Saving…" : "Save response"}<span className="visually-hidden"> for {c.name}</span>
        </button>
      </div>
    </li>
  );
}

/** rec-019 (spec §5; S8, S9): "Shared with you" -- the candidate profiles the placement team shared with this company on the portal, with
 *  the summary only (never a phone, email or salary, R8), the shared resume and the company's response. */
export default function EmployerSharedProfilesPanel() {
  const [data, setData] = useState<PortalPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [reloads, setReloads] = useState(0);
  const [notice, setNotice] = useState<Notice>(null);
  const headingId = `${useId()}-shared`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(employerSharesUrl(offset), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isPortalPage(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [offset, reloads]);

  const answered = (next: PortalItem | null, text: string) => {
    if (next) setData((d) => d && { ...d, items: d.items.map((i) => (i.id === next.id ? next : i)) });
    setNotice({ text, failed: !next });
  };
  return (
    <section className="action-card" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Shared with you{data ? ` (${data.total})` : ""}</h3>
      <p className="muted" style={{ margin: 0 }}>Candidate profiles our placement team has shared with your company.</p>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "6px 0 0" }}>{notice.text}</p>}
      </div>
      {failed ? (
        <div>
          <p className="form-error" role="alert">Unable to load the shared profiles.</p>
          <button type="button" className="btn secondary small" onClick={() => setReloads((n) => n + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status">Loading shared profiles…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No profiles have been shared with you yet.</p>
      ) : (
        <>
          <ul aria-label="Shared profiles" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((item) => <Profile key={item.id} item={item} onAnswered={answered} />)}
          </ul>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Shared profile pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(data.offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
