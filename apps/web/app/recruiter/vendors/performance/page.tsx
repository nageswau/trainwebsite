import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { VendorPerformanceTable } from "@/components/RecruiterVendorPerformance";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";
import { performancePageUrl, type VendorPerformancePage } from "@/lib/vendorCommercials";

// pob-012 (DEC-SCOPE-433 W6/W9): the vendor performance report. The API is the gate (`commercials.vendor.view`, the company scope).
export default async function VendorPerformancePageRoute({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const { offset: raw } = await searchParams;
  const offset = Math.max(0, Number.parseInt(raw ?? "0", 10) || 0);
  let user: User;
  let data: VendorPerformancePage;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<VendorPerformancePage>(performancePageUrl(offset))]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Vendors</div>
            <h2>Vendor performance</h2>
            <p className="muted">How fast we share candidates with each vendor, how those candidates convert, and what is owed. Open a vendor to see the rows behind each figure.</p>
          </div>
          <Link className="btn secondary small" href="/recruiter/vendors">Back to vendors</Link>
        </div>
        <VendorPerformanceTable data={data} offset={offset} />
      </div>
    </PortalShell>
  );
}
