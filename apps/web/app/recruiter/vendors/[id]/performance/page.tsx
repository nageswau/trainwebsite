import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { VendorPerformanceDrillDown } from "@/components/RecruiterVendorPerformance";
import { ApiError, serverApi } from "@/lib/api";
import { COMPANIES_PATH, companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";
import { VENDOR_PERFORMANCE_PATH, type VendorPerformanceDetail, vendorPerformanceUrl } from "@/lib/vendorCommercials";

// pob-012 (DEC-SCOPE-433 W7): one vendor's figures and the rows they are counted from. A 404/422 (unknown, outside the scope, or not a
// vendor) is a plain "not found" -- it never says which.
export default async function VendorPerformanceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let data: VendorPerformanceDetail | null = null;
  try {
    const [me, read] = await Promise.allSettled([serverApi<User>("/api/v1/auth/me"), serverApi<VendorPerformanceDetail>(vendorPerformanceUrl(id))]);
    if (me.status === "rejected") throw me.reason;
    user = me.value;
    if (read.status === "fulfilled") data = read.value;
    else if (!(read.reason instanceof ApiError && (read.reason.status === 404 || read.reason.status === 422))) throw read.reason;
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {data ? (
          <>
            <div className="portal-title">
              <div>
                <div className="eyebrow">Vendor performance</div>
                <h2 style={{ overflowWrap: "anywhere" }}>{data.vendor.name}</h2>
                <p className="muted">{data.vendor.code}{data.vendor_status_label ? ` · ${data.vendor_status_label}` : ""} · all time</p>
              </div>
              <div className="actions">
                <Link className="btn secondary small" href={`${COMPANIES_PATH}/${encodeURIComponent(id)}`}>Open vendor</Link>
                <Link className="btn secondary small" href={VENDOR_PERFORMANCE_PATH}>All vendors</Link>
              </div>
            </div>
            <VendorPerformanceDrillDown data={data} />
          </>
        ) : (
          <div className="action-card">
            <h2>Vendor not found</h2>
            <p><Link href={VENDOR_PERFORMANCE_PATH}>Back to vendor performance</Link></p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
