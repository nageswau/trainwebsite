"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RecruiterInvoiceCard from "@/components/RecruiterInvoiceCard";
import { inr, type Invoice, type InvoicePage, invoicesUrl, isInvoicePage, isReceivableView, RECEIVABLE_TABS, RECEIVABLES_LIMIT, type ReceivableView } from "@/lib/recruiterRevenue";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<ReceivableView, string> = {
  outstanding: "No invoices are waiting for payment.", overdue: "No invoices are overdue.", paid: "No invoices are fully paid yet.", cancelled: "No cancelled invoices.",
};

/** rec-031 (spec §4): the caller's receivables -- Outstanding (soonest due first), Overdue, Paid and Cancelled, with counts and the
 *  outstanding total. The tab, page and an optional company live in the URL, so refresh and Back keep the place. The API scopes the
 *  rows; payments are recorded on the requirement's Revenue section. */
export default function RecruiterReceivablesPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("view");
  const view: ReceivableView = isReceivableView(raw) ? raw : "outstanding";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const companyId = params.get("company_id") ?? undefined;
  const requestUrl = invoicesUrl(view, offset, companyId);
  const [data, setData] = useState<InvoicePage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<Invoice>(requestUrl, controller.signal)
      .then((body) => {
        if (!isInvoicePage(body)) throw new Error("Invoices without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextView: ReceivableView, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextView !== "outstanding") next.set("view", nextView);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    if (companyId) next.set("company_id", companyId);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Receivable lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {RECEIVABLE_TABS.map(([key, label]) => {
          const n = data?.counts[key];
          return (
            <button key={key} type="button" aria-current={view === key ? "page" : undefined} className={`btn small${view === key ? "" : " secondary"}`} onClick={() => go(key)}>
              {label}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      {data && !failed && <p style={{ margin: "12px 0 0" }}><strong>Outstanding in total: {inr(data.outstanding_total)}</strong></p>}
      {failed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load invoices.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading invoices…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          <ul aria-label="Invoices" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((i) => <RecruiterInvoiceCard key={i.id} invoice={i} showRequirement />)}
          </ul>
          {data.total > RECEIVABLES_LIMIT && (
            <nav aria-label="Invoice pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(view, Math.max(0, offset - RECEIVABLES_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(view, offset + RECEIVABLES_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
