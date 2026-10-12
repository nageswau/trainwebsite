import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import InvestmentForm from "@/components/InvestmentForm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate, formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import {
  INVESTMENT_STATUS_LABEL,
  INVESTMENT_VERTICAL_LABEL,
  investmentsUrl,
  investorText,
  investmentUrl,
  MANAGEMENT_INVESTMENTS,
  roiText,
  rupees,
  type Investment,
  type InvestmentPage,
} from "@/lib/investments";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";

const NO_FILTERS = { date_from: "", date_to: "", vertical: "", status: "", offset: 0 };

// mgmt-014 (§23's eleven fields, MI13): one investment, its ROI and who recorded and last changed it, with the edit form. Partner-only:
// the API's 401/403 is the access card; an unknown id is "not found". The register read supplies the active partners for the form.
export default async function ManagementInvestmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let investment: Investment;
  let investors: InvestmentPage["investors"];
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
    [investment, { investors }] = await Promise.all([serverApi<Investment>(investmentUrl(id)), serverApi<InvestmentPage>(investmentsUrl(NO_FILTERS))]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) {
      return (
        <div className="section">
          <div className="container card">
            <h1>Investment not found</h1>
            <p>This investment does not exist. It may have been mistyped.</p>
            <Link className="btn" href={MANAGEMENT_INVESTMENTS}>Back to investments</Link>
          </div>
        </div>
      );
    }
    return accessUnavailable(e, "/admin/login");
  }
  const rows: [string, React.ReactNode][] = [
    ["Investment ID", investment.code],
    ["Date", formatCalendarDate(investment.invested_on)],
    ["Investor / partner", investorText(investment)],
    ["Amount", rupees(investment.amount)],
    ["Purpose", investment.purpose],
    ["Business vertical", INVESTMENT_VERTICAL_LABEL[investment.vertical] ?? investment.vertical],
    ["Expected return", rupees(investment.expected_return)],
    ["Actual return", rupees(investment.actual_return)],
    ["Status", INVESTMENT_STATUS_LABEL[investment.status] ?? investment.status],
    ["ROI", roiText(investment.roi)],
    ["Notes", investment.notes ?? "—"],
  ];
  const stamp = (who: Investment["created_by"], at: string) => `${who.full_name} · ${formatDateTimeIn(at, SCHOOL_TIME_ZONE, true)}`;
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MANAGEMENT_INVESTMENTS}>Investments &amp; ROI</Link></div>
            <h2>{investment.code} · {investment.purpose}</h2>
          </div>
        </div>
        <section className="action-card" aria-label="Investment record" style={{ display: "grid", gap: 12 }}>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, margin: 0 }}>
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt className="muted" style={{ fontSize: 13 }}>{label}</dt>
                <dd style={{ margin: 0, fontWeight: 700, overflowWrap: "anywhere", whiteSpace: label === "Notes" ? "pre-line" : undefined }}>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Recorded by {stamp(investment.created_by, investment.created_at)}. Last changed by {stamp(investment.updated_by, investment.updated_at)} (India time).
          </p>
        </section>
        <InvestmentForm investors={investors} investment={investment} />
      </div>
    </PortalShell>
  );
}
