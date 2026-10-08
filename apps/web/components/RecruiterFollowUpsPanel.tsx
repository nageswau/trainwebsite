"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RecruiterFollowUpItem from "@/components/RecruiterFollowUpItem";
import { formatCalendarDate } from "@/lib/formatDate";
import { DUE_TABS, followUpsUrl, isFollowUpListPage, LIST_LIMIT, type Due, type FollowUpListPage, type RecFollowUp } from "@/lib/recruiterFollowUps";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<Due, string> = {
  today: "Nothing due today and nothing overdue.", overdue: "No overdue follow-ups.", upcoming: "No upcoming follow-ups.",
};

/** rec-024 (spec §4; AC1, FU2): the daily follow-up list EVID-018 §18 asks the CRM to generate -- Today (due today + overdue, IST), Overdue
 *  and Upcoming, oldest due first. The tab and page live in the URL, so refresh keeps the place. The API scopes the rows (a recruiter's
 *  own companies, a manager's team) and decides every action through `can_change`. */
export default function RecruiterFollowUpsPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("due");
  const due: Due = raw === "overdue" || raw === "upcoming" ? raw : "today";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = followUpsUrl(due, offset);
  const [data, setData] = useState<FollowUpListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecFollowUp>(requestUrl, controller.signal)
      .then((body) => {
        if (!isFollowUpListPage(body)) throw new Error("Follow-ups without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextDue: Due, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextDue !== "today") next.set("due", nextDue);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    setNotice(null);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Follow-up lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {DUE_TABS.map(([key, label]) => {
          const n = data?.counts[key];
          return (
            <button key={key} type="button" aria-current={due === key ? "page" : undefined} className={`btn small${due === key ? "" : " secondary"}`} onClick={() => go(key)}>
              {label}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      {data && due === "today" && <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>Due on {formatCalendarDate(data.day)} (IST), plus everything overdue.</p>}
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "8px 0 0" }}>{notice.text}</p>}
      </div>
      {failed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading follow-ups…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[due]}</p>
      ) : (
        <>
          <ul aria-label="Follow-ups" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((fu) => (
              <RecruiterFollowUpItem key={fu.id} followUp={fu} card onChanged={(_, text) => { setNotice({ text, failed: false }); reload(); }}
                onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
            ))}
          </ul>
          {data.total > LIST_LIMIT && (
            <nav aria-label="Follow-up pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(due, Math.max(0, offset - LIST_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(due, offset + LIST_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
