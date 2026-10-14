import Link from "next/link";
import type { ReactNode } from "react";

import { formatCalendarDate } from "@/lib/formatDate";
import { STATUS_LABEL as DISCUSSION_STATUS, statusClass as discussionClass } from "@/lib/managementDiscussions";
import { formatMonth } from "@/lib/managementExpenses";
import { RAG_LABEL } from "@/lib/managementHealth";
import { URGENT_HREF, changeText, firstName, greeting, type ManagementHome as Home } from "@/lib/managementHome";
import { formatInr } from "@/lib/managementLedger";
import { KIND_LABEL, STATUS_LABEL as MEETING_STATUS, istTime, statusClass as meetingClass } from "@/lib/managementMeetings";
import { BANDS, PRIORITY_LABEL } from "@/lib/managementTasks";

// HM11: the open bands' counts, with the tasks page's own labels.
const OPEN_BANDS = (["overdue", "today", "week", "later"] as const).map((band) => ({ band, label: BANDS.find((b) => b.band === band)!.label }));
const PILL = { green: "status", amber: "status pending", red: "status error" } as const;
const money = (amount: string | null | undefined) => (amount == null ? "Not entered" : formatInr(amount));

function Panel({ id, title, more, children }: { id: string; title: string; more?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel home-panel" aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      {children}
      {more && <p className="home-more">{more}</p>}
    </section>
  );
}

const Empty = ({ children }: { children: ReactNode }) => <p className="muted home-empty">{children}</p>;

// mgmt-031 (EVID-017 §31, spec HM1-HM14): the partner home -- greeting and month, today's snapshot, then the nine panels, each a
// summary of the page it links to. Server-rendered from GET /management/home; the API leaves the money out for the super admin, so
// whatever is absent is simply not drawn (no ₹ ever reaches their screen).
export default function ManagementHome({ data, userName, now }: { data: Home; userName: string; now?: Date }) {
  const { snapshot: s, financial_position: position, targets, growth, next_plan: plan } = data;
  const changed = growth.factors.filter((f) => f.change !== null);
  const unchanged = growth.factors.length - changed.length;
  const tiles: { label: string; value: string; note?: string }[] = [
    ...(s.revenue !== undefined ? [{ label: "Revenue", value: formatInr(s.revenue) }, { label: "Expenses", value: formatInr(s.expenses!) }, { label: "Profit", value: formatInr(s.profit!) }] : []),
    ...(s.cash ? [{ label: "Cash", value: money(s.cash.amount), note: s.cash.month ? `as of ${formatMonth(s.cash.month)}` : undefined }] : []),
    { label: "Students", value: s.students.toLocaleString("en-IN") },
    { label: "Applications", value: s.applications.toLocaleString("en-IN"), note: "this month" },
    { label: "Enrollments", value: s.enrollments.toLocaleString("en-IN"), note: "this month" },
  ];
  return (
    <div className="home" id="this-month">
      <div className="home-greeting">
        <h2>{greeting(now)}, {firstName(userName)}</h2>
        <p className="eyebrow">{data.label}</p>
      </div>
      <ul className="metric-grid snapshot-tiles home-tiles" aria-label="Today's business snapshot">
        {tiles.map((t) => (
          <li key={t.label} className="metric">
            <span>{t.label}</span>
            <strong>{t.value}</strong>
            {t.note && <small className="muted">{t.note}</small>}
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: 13 }}>
        {/* QA31-03: the operational home never speaks of money */}
        {s.revenue !== undefined
          ? `Money, applications and enrollments are for ${data.label} to date (India time); cash is the latest balance entered.`
          : `Applications and enrollments are for ${data.label} to date (India time).`}
      </p>

      <div className="home-panels">
        <Panel id="home-urgent" title="Urgent issues">
          {data.urgent.length === 0 ? <Empty>No urgent issues.</Empty> : (
            <ul className="home-list">
              {data.urgent.map((u) => (
                <li key={u.key}>
                  <Link href={URGENT_HREF[u.key]}>{u.label}: {u.amount !== undefined ? formatInr(u.amount) : u.count}</Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel id="home-decisions" title="Pending decisions" more={<Link href="/management/discussions#pending-decisions">All {data.pending_decisions.total} pending decisions</Link>}>
          {data.pending_decisions.items.length === 0 ? <Empty>No pending decisions.</Empty> : (
            <ul className="home-list">
              {data.pending_decisions.items.map((d) => (
                <li key={d.id}>
                  <Link href={`/management/discussions/${d.id}`}>{d.topic}</Link>
                  <span className="muted"> · {d.responsible?.full_name ?? "Unassigned"}{d.deadline ? ` · due ${formatCalendarDate(d.deadline)}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* QA31-01: the first five, with the day's total on the calendar link */}
        <Panel id="home-meetings" title="Today's meetings" more={<Link href="/management/meetings">{data.meetings.total > data.meetings.items.length ? `All ${data.meetings.total} meetings today` : "Open the calendar"}</Link>}>
          {data.meetings.items.length === 0 ? <Empty>No meetings today.</Empty> : (
            <ul className="home-list">
              {data.meetings.items.map((m) => (
                <li key={m.id}>
                  <span className="no-wrap">{istTime(m.starts_at)}</span> <Link href={`/management/meetings/${m.id}`}>{m.title}</Link>
                  <span className="muted"> · {KIND_LABEL[m.kind]}</span> <span className={meetingClass(m.status)}>{MEETING_STATUS[m.status]}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel id="home-targets" title="Target vs actual" more={<Link href={targets ? `/management/plans/${targets.month}` : "/management/plans"}>{targets ? `Open the ${targets.label} plan` : `Plan ${data.label}`}</Link>}>
          {!targets ? <Empty>No plan for {data.label} yet.</Empty> : (
            <>
              {targets.rows.length === 0 ? <Empty>No KPI targets in this plan.</Empty> : (
                <ul className="home-list">
                  {targets.rows.map((r) => (
                    <li key={r.item_id}>
                      {r.text}: {r.unit === "inr" ? `${formatInr(r.actual)} of ${formatInr(r.target)}` : `${Number(r.actual).toLocaleString("en-IN")} of ${Number(r.target).toLocaleString("en-IN")}`} <strong>{r.achievement}%</strong>
                    </li>
                  ))}
                </ul>
              )}
              {targets.row_total > targets.rows.length && <p className="muted">and {targets.row_total - targets.rows.length} more</p>}
              {targets.free_text.total > 0 && <p className="muted">Other items: {targets.free_text.done} of {targets.free_text.total} done</p>}
            </>
          )}
        </Panel>

        {position && (
          <Panel id="home-position" title="Financial position" more={<Link href={position.balance_month ? `/management/accounts?month=${position.balance_month}` : "/management/accounts"}>Open accounts</Link>}>
            <dl className="home-figures">
              <dt>Receivables</dt><dd>{formatInr(position.receivables)}</dd>
              <dt>of which overdue</dt><dd>{formatInr(position.receivables_overdue)}</dd>
              <dt>Pending invoices</dt><dd>{position.pending_invoices.count} · {formatInr(position.pending_invoices.amount)}</dd>
              <dt>Cash/bank</dt><dd>{money(position.cash_bank)}</dd>
              <dt>Payables</dt><dd>{money(position.payables)}</dd>
              <dt>Tax liabilities</dt><dd>{money(position.tax_liabilities)}</dd>
            </dl>
            <p className="muted" style={{ fontSize: 13 }}>{position.balance_month ? `Balances entered for ${formatMonth(position.balance_month)}.` : "No balances entered yet."}</p>
          </Panel>
        )}

        <Panel id="home-growth" title="Business growth" more={<Link href="/management/health">Open the health score</Link>}>
          {growth.score === null ? <Empty>Not enough data to score {formatMonth(growth.month)}.</Empty> : (
            <>
              <p>
                {formatMonth(growth.month)}: <strong>{growth.score}/100</strong> {growth.rag && <span className={PILL[growth.rag]}>{RAG_LABEL[growth.rag]}</span>}
              </p>
              {/* QA31-02: only the factors with a month-on-month change; the others are counted, not listed as "—" */}
              {changed.length > 0 && (
                <ul className="home-list">
                  {changed.map((f) => (
                    <li key={f.key}>
                      {f.label}: <span>{changeText(f.change)}</span> {f.rag && <span className={PILL[f.rag]}>{RAG_LABEL[f.rag]}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {unchanged > 0 && <p className="muted">{unchanged === 1 ? "1 factor has" : `${unchanged} factors have`} no month-on-month comparison yet.</p>}
            </>
          )}
        </Panel>

        <Panel id="home-tasks" title="My tasks" more={<Link href="/management/tasks">All my tasks</Link>}>
          <p className="muted">{OPEN_BANDS.map((b) => `${b.label}: ${data.my_tasks.counts[b.band]}`).join(" · ")}</p>
          {data.my_tasks.items.length === 0 ? <Empty>No open tasks for you.</Empty> : (
            <ul className="home-list">
              {data.my_tasks.items.map((t) => (
                <li key={t.id}>
                  <Link href={`/management/tasks/${t.id}`}>{t.title}</Link>
                  <span className="muted"> · {PRIORITY_LABEL[t.priority]} · due {formatCalendarDate(t.deadline)}{t.band === "overdue" ? " · overdue" : t.band === "completed" ? " · completed" : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel id="home-discussions" title="Recent discussions" more={<Link href="/management/discussions">All {data.recent_discussions.total} discussions</Link>}>
          {data.recent_discussions.items.length === 0 ? <Empty>No discussions yet.</Empty> : (
            <ul className="home-list">
              {data.recent_discussions.items.map((d) => (
                <li key={d.id}>
                  <Link href={`/management/discussions/${d.id}`}>{d.topic}</Link>
                  <span className="muted"> · {formatCalendarDate(d.discussion_date)}</span> <span className={discussionClass(d.status)}>{DISCUSSION_STATUS[d.status]}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel id="home-next-plan" title="Next month plan" more={<Link href={plan.plan ? `/management/plans/${plan.month}` : "/management/plans"}>{plan.plan ? `Open the ${plan.label} plan` : `Plan ${plan.label}`}</Link>}>
          {!plan.plan ? <Empty>No plan for {plan.label} yet.</Empty> : (
            <p>
              {plan.label}: {plan.plan.item_count} items, {plan.plan.kpi_count} with a KPI target <span className="badge">{plan.plan.status[0].toUpperCase() + plan.plan.status.slice(1)}</span>
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}
