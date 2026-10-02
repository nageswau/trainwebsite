"use client";

import { useCallback, useEffect, useState } from "react";
import AdminDepositActionForm, { ACTION_LABELS, AdminDeposit, DEPOSIT_ACTIONS_FOR, DepositAction, DEPOSITS_URL } from "./AdminDepositActionForm";
import { isPage, Page } from "@/lib/apiErrors";
import { DEPOSIT_STATUS_LABELS, formatInr } from "@/lib/agentApplications";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

type Tab = "paid" | "remitted" | "refunded" | "pending" | "all";
const TABS: { status: Tab; label: string }[] = [
  { status: "paid", label: "Paid" },
  { status: "remitted", label: "Remitted" },
  { status: "refunded", label: "Refunded" },
  { status: "pending", label: "Awaiting payment" },
  { status: "all", label: "All" },
];
const PAGE_SIZE = 20;
const DONE: Record<DepositAction, string> = { remit: "Remittance recorded", refund: "Refund recorded" };

// AGN-011 (DEC-SCOPE-057 §4.7): Overseas Admin's Agent deposits. Deposits are collected through EduSphere Razorpay; finance remits them
// to the university outside the system and refunds by hand (D12), and this screen records both. One status tab at a time, 20 per page,
// tab and page in the URL (the AgentApprovalPanel pattern). `canAct` is false for super_admin, who reads only (D5).
export default function AdminAgentDepositsPanel({ canAct }: { canAct: boolean }) {
  const [status, setStatus] = useState<Tab>("paid");
  const [offset, setOffset] = useState(0);
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<Page<AdminDeposit> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [acting, setActing] = useState<{ id: string; action: DepositAction } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    if (tab && TABS.some((t) => t.status === tab)) setStatus(tab as Tab);
    const pageNumber = Number.parseInt(params.get("page") ?? "1", 10);
    if (Number.isFinite(pageNumber) && pageNumber > 1) setOffset((pageNumber - 1) * PAGE_SIZE);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    ["tab", "page"].forEach((key) => params.delete(key));
    if (status !== "paid") params.set("tab", status);
    if (offset > 0) params.set("page", String(offset / PAGE_SIZE + 1));
    const search = params.toString();
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`);
  }, [ready, status, offset]);

  const load = useCallback(() => {
    if (!ready) return;
    setLoadFailed(false);
    setData(null);
    fetch(`${DEPOSITS_URL}?status=${status}&limit=${PAGE_SIZE}&offset=${offset}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: unknown) => (isPage<AdminDeposit>(body) ? setData(body) : setLoadFailed(true)))
      .catch(() => setLoadFailed(true));
  }, [ready, status, offset]);

  useEffect(load, [load]);

  function showTab(next: Tab) {
    setActing(null);
    setNotice(null);
    setStatus(next);
    setOffset(0);
  }
  function done(deposit: AdminDeposit, action: DepositAction) {
    setActing(null);
    setNotice(`${DONE[action]} for ${deposit.student}.`);
    load(); // the deposit may have left this tab
  }

  const tab = TABS.find((t) => t.status === status) ?? TABS[0];
  return (
    <div className="action-card">
      <h3>Agent deposits</h3>
      {/* Always mounted so screen readers announce the text when it arrives. */}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginTop: 8 } : undefined}>
        {notice}
      </div>
      <div role="group" aria-label="Deposit status" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {TABS.map((t) => (
          <button key={t.status} type="button" className={t.status === status ? "btn small" : "btn secondary small"} aria-pressed={t.status === status} onClick={() => showTab(t.status)}>
            {t.label}
          </button>
        ))}
      </div>
      <section aria-labelledby="agent-deposits-heading" style={{ marginTop: 16 }}>
        <h4 id="agent-deposits-heading">{tab.label}</h4>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">
              Unable to load deposits.
            </p>
            <button type="button" className="btn secondary small" onClick={load}>
              Retry
            </button>
          </>
        ) : data === null ? (
          <p className="muted" aria-busy="true">
            Loading deposits…
          </p>
        ) : data.items.length === 0 ? (
          <p className="muted">No deposits with this status.</p>
        ) : (
          <>
            <div className="grid two">
              {data.items.map((d) => (
                <div className="card" key={d.id} style={{ overflowWrap: "anywhere" }}>
                  <span className="badge">{DEPOSIT_STATUS_LABELS[d.status]}</span>
                  <h5 style={{ marginTop: 10, fontSize: "1rem" }}>{d.student}</h5>
                  <p className="muted" style={{ fontSize: 13 }}>
                    {d.agency ?? "Unknown agency"} · {d.university}
                  </p>
                  <dl className="card-stack">
                    <dt>Amount</dt>
                    <dd>{d.amount ? formatInr(d.amount) : "—"}</dd>
                    {d.paid_at && (
                      <>
                        <dt>Paid</dt>
                        <dd>
                          {formatDateTimeIn(d.paid_at, viewerTimeZone(), true)} · {d.paid_by ?? "—"}
                        </dd>
                      </>
                    )}
                    {d.remitted_at && (
                      <>
                        <dt>Remitted</dt>
                        <dd>
                          {d.remitted_at} · Ref. {d.remittance_reference}
                        </dd>
                      </>
                    )}
                    {d.refunded_at && d.refund_amount && (
                      <>
                        <dt>Refunded</dt>
                        <dd>
                          {formatInr(d.refund_amount)} on {d.refunded_at} · {d.refund_reason}
                        </dd>
                      </>
                    )}
                  </dl>
                  {d.unlinked_paid_payments > 0 && (
                    <p className="form-warning" style={{ fontSize: 13 }}>
                      {d.unlinked_paid_payments === 1 ? "1 other captured payment" : `${d.unlinked_paid_payments} other captured payments`} for this deposit{" "}
                      {d.unlinked_paid_payments === 1 ? "needs" : "need"} a manual refund.
                    </p>
                  )}
                  {canAct && acting?.id === d.id ? (
                    <AdminDepositActionForm deposit={d} action={acting.action} onDone={(next) => done(next, acting.action)} onCancel={() => setActing(null)} />
                  ) : (
                    canAct && (
                      <div className="actions">
                        {DEPOSIT_ACTIONS_FOR[d.status].map((action) => (
                          <button
                            key={action}
                            type="button"
                            className={action === "remit" ? "btn small" : "btn secondary small"}
                            aria-label={`${ACTION_LABELS[action]} for ${d.student}`}
                            onClick={() => {
                              setNotice(null);
                              setActing({ id: d.id, action });
                            }}
                          >
                            {ACTION_LABELS[action]}
                          </button>
                        ))}
                      </div>
                    )
                  )}
                </div>
              ))}
            </div>
            <nav aria-label="Deposit pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  );
}
