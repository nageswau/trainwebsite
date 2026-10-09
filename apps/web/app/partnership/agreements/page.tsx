import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import {
  type Agreement,
  type AgreementFilters,
  agreementListQuery,
  agreementPageHref,
  AGREEMENT_STATUSES,
  AGREEMENT_TYPES,
  AGREEMENTS_PATH,
  AGREEMENTS_URL,
  dateText,
  EXCLUSIVITY,
  expiryText,
} from "@/lib/universityAgreements";

// upc-014 (AG18): the §32 "MoU & Agreements" menu -- every agreement, soonest expiry first, filtered by status (Expiring and Expired
// included), type and a MoU-number / university search. Filters and paging live in the URL; a plain GET form, so it works without
// JavaScript. Agreements are created and moved on each university's page. The API is the gate: any other role gets its 403 here.
export default async function AgreementsPage({ searchParams }: { searchParams: Promise<AgreementFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<Agreement>;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<Agreement>>(`${AGREEMENTS_URL}?${agreementListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Boolean(filters.status || filters.agreement_type || filters.q?.trim());
  const end = page.offset + page.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">MoU &amp; Agreements</div>
            <h2>University agreements</h2>
            <p className="muted">Every MoU and agreement, soonest expiry first. Create, approve, sign and renew them from each university&apos;s page.</p>
          </div>
        </div>
        <form method="get" action={AGREEMENTS_PATH} className="card" aria-label="Filter agreements" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="ag-filter-status">Status</label>
            <select id="ag-filter-status" name="status" defaultValue={filters.status ?? ""}>
              <option value="">Any status</option>
              {Object.entries(AGREEMENT_STATUSES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="ag-filter-type">Type</label>
            <select id="ag-filter-type" name="agreement_type" defaultValue={filters.agreement_type ?? ""}>
              <option value="">Any type</option>
              {Object.entries(AGREEMENT_TYPES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0, flex: "1 1 14rem" }}>
            <label htmlFor="ag-filter-q">Search</label>
            <input id="ag-filter-q" name="q" type="search" maxLength={100} defaultValue={filters.q ?? ""} placeholder="MoU number, university or code" />
          </div>
          <button type="submit" className="btn secondary small">Apply</button>
          {filtered && <Link className="btn ghost small" href={AGREEMENTS_PATH}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No agreements match these filters." : "No agreements recorded yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={agreementPageHref(filters, 0)}>Go to the first page</Link>
          </>
        ) : (
          <div className="telecaller-list">
            <div className="table-wrap" role="region" aria-label="University agreements" tabIndex={0}>
              <table>
                <caption className="visually-hidden">University agreements, {page.total} in total</caption>
                <thead>
                  <tr>
                    <th scope="col">MoU number</th><th scope="col">University</th><th scope="col">Type</th><th scope="col">Status</th>
                    <th scope="col">Period</th><th scope="col">Exclusivity</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((a) => {
                    const expiry = expiryText(a);
                    return (
                      <tr key={a.id}>
                        <td data-label="MoU number">{a.mou_number}</td>
                        {/* one wrapper per mixed cell -- on a phone each cell is a flex row (upc-026 QA-01) */}
                        <td data-label="University">
                          <span><Link href={universityPath(a.university.id)}>{a.university.name}</Link> <span className="muted" style={{ whiteSpace: "nowrap" }}>{a.university.university_code}</span></span>
                        </td>
                        <td data-label="Type">{a.type_label}</td>
                        <td data-label="Status"><span><span className="badge">{a.status_label}</span>{expiry && <span className="muted"> {expiry}</span>}</span></td>
                        <td data-label="Period"><span>{dateText(a.start_date)} – {dateText(a.expiry_date)}</span></td>
                        <td data-label="Exclusivity">{EXCLUSIVITY[a.exclusivity] ?? a.exclusivity}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {page.total > page.limit && (
              <nav aria-label="Agreement pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={agreementPageHref(filters, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={agreementPageHref(filters, end)}>Next</Link>}
              </nav>
            )}
          </div>
        )}
      </div>
    </PortalShell>
  );
}
