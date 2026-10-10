import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { withBadge } from "@/lib/navigation";
import { ALERT_READERS, ALERTS_PATH, ALERTS_URL, type AlertPage, alertsHref, chosenKind, emptyText, KIND_TABS, PAGE_SIZE } from "@/lib/partnershipAlerts";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

type Search = { kind?: string; offset?: string };

// upc-015 (§14, §6, §20, §32 "Alerts"): the caller's own partnership alerts, newest first, with kind tabs. Each alert was also emailed.
// Opening an unread alert marks it read before it navigates (the shared notification list), so the badge is right on return.
export default async function PartnershipAlertsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const kind = chosenKind(search.kind);
  const offset = Math.max(0, Math.floor(Number(search.offset) || 0));
  let user: User;
  let data: AlertPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!ALERT_READERS.has(user.role)) return accessDenied(user, "Partnership alerts access required");
    const query = new URLSearchParams({ ...(kind === "all" ? {} : { kind }), limit: String(PAGE_SIZE), offset: String(offset) });
    data = await serverApi<AlertPage>(`${ALERTS_URL}?${query}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const last = data.offset + data.items.length;
  return (
    <PortalShell nav={withBadge(nav, ALERTS_PATH, data.unread)} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Alerts</div>
            <h2>Alerts</h2>
            <p className="muted">Agreement expiries, delayed milestones and overdue follow-ups for your universities. Each alert is also sent to you by email.</p>
          </div>
        </div>
        <nav className="actions" aria-label="Alert kind" style={{ flexWrap: "wrap", margin: "0 0 12px" }}>
          {KIND_TABS.map((t) => (
            <Link key={t.key} className={`btn small ${t.key === kind ? "" : "secondary"}`} aria-current={t.key === kind ? "page" : undefined} href={alertsHref(t.key)}>
              {t.label}
            </Link>
          ))}
        </nav>
        <div className="card">
          {data.items.length === 0 && data.total > 0 ? (
            <p className="empty">This page is past the end of the list. <Link href={alertsHref(kind)}>Go to the first page</Link></p>
          ) : (
            <SchoolNotificationList notifications={data.items} readBeforeOpen emptyText={emptyText(kind)} />
          )}
        </div>
        {data.total > data.limit && (
          <nav className="actions" aria-label="Pages" style={{ marginTop: 12, alignItems: "center" }}>
            {data.offset > 0 && <Link className="btn ghost small" href={alertsHref(kind, Math.max(0, data.offset - data.limit))}>Previous</Link>}
            <span className="muted">{data.offset + 1}–{last} of {data.total}</span>
            {last < data.total && <Link className="btn ghost small" href={alertsHref(kind, last)}>Next</Link>}
          </nav>
        )}
      </div>
    </PortalShell>
  );
}
