"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RecruiterCandidateTaskItem from "@/components/RecruiterCandidateTaskItem";
import { formatCalendarDate } from "@/lib/formatDate";
import { isTaskListPage, LIST_LIMIT, myTasksUrl, type CandidateTask, type TaskListPage } from "@/lib/recruiterCandidateTasks";
import { DUE_TABS, type Due } from "@/lib/recruiterFollowUps";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<Due, string> = { today: "Nothing due today and nothing overdue.", overdue: "No overdue tasks.", upcoming: "No upcoming tasks." };

/** hrc-016 (T8, AC2): the caller's own open candidate tasks -- Today (due today + overdue, IST), Overdue and Upcoming, oldest due first --
 *  the rec-024 daily list's shape. The tab and page live in the URL, so refresh keeps the place. */
export default function RecruiterMyTasksPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("due");
  const due: Due = raw === "overdue" || raw === "upcoming" ? raw : "today";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = myTasksUrl(due, offset);
  const [data, setData] = useState<TaskListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<CandidateTask>(requestUrl, controller.signal)
      .then((body) => {
        if (!isTaskListPage(body)) throw new Error("Tasks without counts");
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
      <nav aria-label="Task lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
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
          <p className="form-error" role="alert">Unable to load tasks.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading tasks…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[due]}</p>
      ) : (
        <>
          <ul aria-label="My tasks" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((task) => (
              <RecruiterCandidateTaskItem key={task.id} task={task} card onChanged={(_, text) => { setNotice({ text, failed: false }); reload(); }}
                onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
            ))}
          </ul>
          {data.total > LIST_LIMIT && (
            <nav aria-label="Task pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
