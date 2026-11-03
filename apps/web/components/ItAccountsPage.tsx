import { accessUnavailable } from "@/components/AccessUnavailable";
import ItAccountsWorkspace from "@/components/ItAccountsWorkspace";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { IT_ADMIN_ACCOUNTS, MANAGEMENT_IT_ACCOUNTS, accountsParams, accountsReport, accountsUrl, type AccountsPage } from "@/lib/itAccounts";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { PORTAL_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

const UNAVAILABLE = "IT accounts are unavailable right now. Please try again.";

// itc-017 (DEC-SCOPE-367 F2): one body behind the IT Admin's /it/admin/accounts and the finance tier's /management/it-accounts. The API
// decides who may read (a `payments.view` holder in IT; anyone else 403, shown as the access card); a 422 (bad filters) is shown above the
// form. Each shell keeps its own sidebar; super_admin keeps theirs.
export default async function ItAccountsPage({ shell, searchParams }: {
  shell: "it" | "management"; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const search = await searchParams;
  const loginHref = shell === "it" ? "/it/login" : "/admin/login";
  let user: User;
  let nav: NavItem[];
  let roleLabel: string;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role === "super_admin") {
      [nav, roleLabel] = [SUPER_ADMIN_NAV, "Super Administrator"];
    } else if (shell === "management") {
      const me = await serverApi<ManagementMe>("/api/v1/management/me");
      [nav, roleLabel] = [managementNavFor(me.tiers), MANAGEMENT_ROLE_LABEL[me.role] ?? me.role];
    } else {
      [nav, roleLabel] = [PORTAL_NAV["it/admin"], "IT Administrator"];
    }
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  const report = accountsReport(search.report);
  const params = accountsParams(report, search);
  let page: AccountsPage | null = null;
  let error = "";
  try {
    page = await serverApi<AccountsPage>(accountsUrl(report, params));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, loginHref);
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">IT training fees</div>
            <h2>Accounts</h2>
            <p className="muted">Collections, what is still owed, overdue installments, the receipts register and refunds for IT enrolment fees. Dates are India time (IST). To record a payment, a refund or a correction, open the student&apos;s fee account.</p>
          </div>
        </div>
        <ItAccountsWorkspace report={report} page={page} error={error} params={params} basePath={shell === "it" ? IT_ADMIN_ACCOUNTS : MANAGEMENT_IT_ACCOUNTS}
          studentLinks={shell === "it" || user.role === "super_admin"} />
      </div>
    </PortalShell>
  );
}
