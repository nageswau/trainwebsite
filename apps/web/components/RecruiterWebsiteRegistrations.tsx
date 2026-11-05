"use client";

import Link from "next/link";

import LocalTime from "@/components/LocalTime";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { CANDIDATES_PATH, personLabel } from "@/lib/recruiterCandidates";
import { CATALOGUE_PAGE_SIZE } from "@/lib/telecallerCatalogue";
import { useUrlList } from "@/lib/useUrlList";
import { CONVERSION_LABEL, VIEWS, VIEW_KEYS, WEBSITE_REGISTRATIONS_URL, type WebsiteRegistration } from "@/lib/websiteRegistrations";

const SLA_HOURS = 24; // DEC-SCOPE-402 N8; the API's `sla_hours` says the same
const NONE = <span className="muted">—</span>;
const SMALL = { fontSize: 13 };

function skillsText(r: WebsiteRegistration) {
  if (!r.skill_count) return NONE;
  const more = r.skill_count - r.skills.length;
  return <>{r.skills.join(", ")}{more > 0 ? ` +${more}` : ""}</>;
}

/** hrc-025 (DEC-SCOPE-402): the candidates the website created, newest first -- who has them, whether they were contacted within the SLA,
 *  the next follow-up and how far they converted. One "Show" filter and the page live in the URL (useUrlList), so refresh and Back keep
 *  the view. A row links to the candidate only for a reader who can open candidates (not the HR Manager, N2). */
export default function RecruiterWebsiteRegistrations() {
  const list = useUrlList<WebsiteRegistration>(WEBSITE_REGISTRATIONS_URL, "view", VIEW_KEYS);
  const { data, loadFailed, reload, filter, offset, go } = list;
  return (
    <div className="action-card wide" aria-busy={data === null && !loadFailed}>
      <p className="muted" style={{ marginTop: 0 }}>Contact target: the first call or message within {SLA_HOURS} hours of registering. Late rows are marked “SLA breached”.</p>
      <div className="field" style={{ maxWidth: 260 }}>
        <label htmlFor="web-reg-view">Show</label>
        <select id="web-reg-view" value={filter} onChange={(e) => go(e.target.value, 0)}>
          <option value="">All registrations</option>
          {VIEWS.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
        </select>
      </div>
      {loadFailed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load website registrations.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading website registrations…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>{filter ? "No website registrations match this filter." : "No website registrations yet."}</p>
      ) : (
        <>
          <div className="table-scroll" role="region" aria-label="Website registrations" tabIndex={0} style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  {["Candidate", "Registered", "Skills", "Location", "Completeness", "Assigned to", "Engagement", "First contact", "Next follow-up", "Conversion"].map((h) => (
                    <th key={h} scope="col">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <th scope="row">
                      {r.can_open ? <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(r.id)}`} style={LINK_STYLE}>{r.name}</Link> : r.name}
                      <div className="muted" style={SMALL}>{r.candidate_code}</div>
                      {r.duplicate_review && <span className="badge status error" style={SMALL}>Duplicate review</span>}
                    </th>
                    <td style={{ whiteSpace: "nowrap" }}><LocalTime value={r.registered_at} time /></td>
                    <td>{skillsText(r)}</td>
                    <td>{r.location ?? NONE}</td>
                    <td>{r.completeness}%</td>
                    <td>{r.owner ? personLabel(r.owner) : <span className="muted">Unassigned</span>}</td>
                    <td>{r.engagement ? <span className="badge">{r.engagement.label}</span> : NONE}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {r.first_contact_at ? <LocalTime value={r.first_contact_at} time /> : <span className="muted">Not contacted</span>}
                      {r.contact_sla === "breached" && <div><span className="badge status error">SLA breached</span></div>}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{r.next_follow_up_at ? <LocalTime value={r.next_follow_up_at} time /> : NONE}</td>
                    <td>{CONVERSION_LABEL[r.conversion]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > CATALOGUE_PAGE_SIZE && (
            <nav aria-label="Website registration pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={SMALL}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(filter, Math.max(0, offset - CATALOGUE_PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(filter, offset + CATALOGUE_PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
