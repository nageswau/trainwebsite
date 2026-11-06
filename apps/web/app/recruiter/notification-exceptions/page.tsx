import { accessUnavailable } from "@/components/AccessUnavailable";
import DeliveryExceptionsPanel from "@/components/DeliveryExceptionsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { type ExceptionPage, listUrl, parseFilters } from "@/lib/notificationExceptions";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// hrc-032 (DEC-SCOPE-412 N8-N10): the API decides who reads it (a `notifications.retry` holder; anyone else 403, shown as the access card).
export default async function DeliveryExceptionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = parseFilters(await searchParams);
  let user: User;
  let page: ExceptionPage;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<ExceptionPage>(listUrl(filters))]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment</div>
            <h2>Delivery exceptions</h2>
            <p className="muted">Recruitment notices and emails that could not be delivered after their automatic attempts.</p>
          </div>
        </div>
        <DeliveryExceptionsPanel key={`${filters.type}-${filters.channel}-${filters.offset}`} page={page} filters={filters} />
      </div>
    </PortalShell>
  );
}
