import Link from "next/link";

import { travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripTable from "@/components/TripTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, PAGE_SIZE, type BdmMe } from "@/lib/bdm";
import { APPROVAL_LABEL, type ApprovalStatus, type TripRow } from "@/lib/bdmTravel";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/travel";

// bdm-010: the BDM's own trips, newest travel date first. The filter and the offset live in the URL (a plain GET form, no JS),
// as bdm-001's team page does; an unknown filter value is ignored rather than sent.
export default async function MyTripsPage({ searchParams }: { searchParams: Promise<{ offset?: string; approval_status?: string }> }) {
  const sp = await searchParams;
  const raw = Number.parseInt(sp.offset ?? "0", 10);
  const offset = Number.isFinite(raw) && raw > 0 ? raw : 0;
  const status = sp.approval_status && sp.approval_status in APPROVAL_LABEL ? (sp.approval_status as ApprovalStatus) : null;
  const query = status ? `approval_status=${status}` : "";
  let me: BdmMe, trips: Page<TripRow>;
  try {
    [me, trips] = await Promise.all([
      serverApi<BdmMe>("/api/v1/bdm/me"),
      serverApi<Page<TripRow>>(`/api/v1/bdm/trips?limit=${PAGE_SIZE}&offset=${offset}${query ? `&${query}` : ""}`),
    ]);
  } catch (e) {
    return travelUnavailable(e, BDM_SIGN_IN, `${PATH}${query ? `?${query}` : ""}`);
  }
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Travel</div>
            <h2>My trips</h2>
            <p className="muted">Plan a trip, send it to {me.bdm_profile.reporting_manager.full_name} for approval, then add expenses once it is approved.</p>
          </div>
          <Link className="btn" href={`${PATH}/new`}>New trip</Link>
        </div>
        <form className="analytics-form" method="get" action={PATH} aria-label="Filter trips">
          <div className="field">
            <label htmlFor="trip-filter">Approval status</label>
            <select id="trip-filter" name="approval_status" defaultValue={status ?? ""}>
              <option value="">All</option>
              {Object.entries(APPROVAL_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <button className="btn secondary" type="submit">Filter</button>
          {status && <Link className="btn ghost" href={PATH}>Clear filter</Link>}
        </form>
        {trips.total === 0 ? (
          status ? (
            <p className="empty" role="status">No trips match this filter. <Link className="text-link" href={PATH}>Clear filter</Link></p>
          ) : (
            <p className="empty" role="status">No trips yet — <Link className="text-link" href={`${PATH}/new`}>create your first trip</Link>.</p>
          )
        ) : trips.items.length === 0 ? (
          <p className="empty" role="status">This page is past the end of your trips. <Link className="text-link" href={PATH}>Go to the first page</Link></p>
        ) : (
          <TripTable page={trips} label="My trips" basePath={PATH} query={query} detailHref={(id) => `${PATH}/${id}`} />
        )}
      </div>
    </PortalShell>
  );
}
