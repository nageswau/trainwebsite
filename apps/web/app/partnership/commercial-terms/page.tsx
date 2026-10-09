import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import {
  type CommissionTermRow,
  COMMISSION_TERMS_PATH,
  COMMISSION_TERMS_URL,
  CURRENCIES,
  rateText,
  scopeText,
  type TermFilters,
  termListQuery,
  termPageHref,
  TRIGGERS,
} from "@/lib/commissionTerms";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

// upc-016 (CM14): the §32 "💰 Commercial Terms" menu -- every commission term, newest first, with its agreement and university, filtered
// by trigger, currency and a MoU-number / university search. RESTRICTED (U2): the API answers 403 to every non-commission role, which
// lands here as the access page. Terms are added and edited inside each agreement on the university's page.
export default async function CommercialTermsPage({ searchParams }: { searchParams: Promise<TermFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<CommissionTermRow>;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<CommissionTermRow>>(`${COMMISSION_TERMS_URL}?${termListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Boolean(filters.trigger || filters.currency || filters.q?.trim());
  const end = page.offset + page.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Commercial Terms · Restricted</div>
            <h2>Commission terms</h2>
            <p className="muted">What each university pays EduSphere under its agreements, newest first. Add and edit terms inside each agreement on the university&apos;s page.</p>
          </div>
        </div>
        <form method="get" action={COMMISSION_TERMS_PATH} className="card" aria-label="Filter commission terms" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="ct-filter-trigger">Trigger</label>
            <select id="ct-filter-trigger" name="trigger" defaultValue={filters.trigger ?? ""}>
              <option value="">Any trigger</option>
              {Object.entries(TRIGGERS).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="ct-filter-currency">Currency</label>
            <select id="ct-filter-currency" name="currency" defaultValue={filters.currency ?? ""}>
              <option value="">Any currency</option>
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0, flex: "1 1 14rem" }}>
            <label htmlFor="ct-filter-q">Search</label>
            <input id="ct-filter-q" name="q" type="search" maxLength={100} defaultValue={filters.q ?? ""} placeholder="MoU number, university or code" />
          </div>
          <button type="submit" className="btn secondary small">Apply</button>
          {filtered && <Link className="btn ghost small" href={COMMISSION_TERMS_PATH}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No commission terms match these filters." : "No commission terms recorded yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={termPageHref(filters, 0)}>Go to the first page</Link>
          </>
        ) : (
          <div className="telecaller-list">
            <div className="table-wrap" role="region" aria-label="Commission terms" tabIndex={0}>
              <table>
                <caption className="visually-hidden">Commission terms, {page.total} in total</caption>
                <thead>
                  <tr>
                    <th scope="col">University</th><th scope="col">Agreement</th><th scope="col">Commission</th><th scope="col">Trigger</th>
                    <th scope="col">Applies to</th><th scope="col">Payment timeline</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((t) => (
                    <tr key={t.id}>
                      {/* one wrapper per mixed cell -- on a phone each cell is a flex row (upc-026 QA-01) */}
                      <td data-label="University">
                        <span><Link href={universityPath(t.university.id)}>{t.university.name}</Link> <span className="muted" style={{ whiteSpace: "nowrap" }}>{t.university.university_code}</span></span>
                      </td>
                      <td data-label="Agreement"><span>{t.agreement.mou_number} <span className="badge">{t.agreement.status_label}</span></span></td>
                      <td data-label="Commission"><span><strong>{rateText(t)}</strong>{t.commission_percent !== null && <span className="muted"> {t.currency}</span>}</span></td>
                      <td data-label="Trigger">{t.trigger_label}</td>
                      <td data-label="Applies to" style={{ overflowWrap: "anywhere" }}>{scopeText(t)}</td>
                      <td data-label="Payment timeline" style={{ overflowWrap: "anywhere" }}>{t.payment_timeline || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.total > page.limit && (
              <nav aria-label="Commission term pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={termPageHref(filters, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={termPageHref(filters, end)}>Next</Link>}
              </nav>
            )}
          </div>
        )}
      </div>
    </PortalShell>
  );
}
