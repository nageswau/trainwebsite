"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import FollowUpItem from "@/components/FollowUpItem";
import { todayIst } from "@/lib/bdmAppointments";
import { formatCalendarDate, isCalendarDate } from "@/lib/formatDate";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";
import { followUpsUrl, isFollowUpPage, LIST_LIMIT, type FollowUp, type FollowUpPage, type View } from "@/lib/telecallerFollowUps";

const EMPTY: Record<View, string> = { day: "No follow-ups due on this day.", overdue: "No overdue follow-ups." };

/** tel-011 (spec §4; AC1, AC2, F1): "Today's follow-ups" (EVID-019 §7) -- the open follow-ups due on a day (today by default, IST),
 *  oldest due first, overdue ones marked -- and the Overdue list. The view, day and page live in the URL, so refresh keeps the place.
 *  A manager (`showTelecaller`) reads their reports' lists; the API's `can_change` decides every action. */
export default function TodayFollowUps({ leadBasePath, showTelecaller }: { leadBasePath: string; showTelecaller: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view: View = params.get("view") === "overdue" ? "overdue" : "day";
  const rawDay = params.get("day") ?? "";
  const day = isCalendarDate(rawDay) ? rawDay : null; // a hand-edited bad day is ignored, never sent (it would only ever be a 422)
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = followUpsUrl(view, day, offset);
  const [data, setData] = useState<FollowUpPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const [today] = useState(todayIst);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<FollowUp>(requestUrl, controller.signal)
      .then((body) => {
        if (!isFollowUpPage(body)) throw new Error("Follow-ups without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(changes: Record<string, string>, nextOffset = 0) {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    else next.delete("offset");
    setNotice(null);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  const shownDay = data?.day ?? day ?? today;
  const dayTab = shownDay === today ? "Today" : formatCalendarDate(shownDay);
  const tabs: [View, string][] = [["day", dayTab], ["overdue", "Overdue"]];
  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", justifyContent: "space-between" }}>
        <nav aria-label="Follow-up lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {tabs.map(([key, label]) => {
            const n = data?.counts[key];
            return (
              <button key={key} type="button" aria-current={view === key ? "page" : undefined} className={`btn small${view === key ? "" : " secondary"}`}
                onClick={() => go({ view: key === "overdue" ? "overdue" : "" })}>
                {label}{n === undefined ? "" : ` (${n})`}
              </button>
            );
          })}
        </nav>
        {view === "day" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="follow-up-day">Day</label>
              <input id="follow-up-day" type="date" value={day ?? today} onChange={(e) => go({ day: e.target.value && e.target.value !== today ? e.target.value : "" })} />
            </div>
            {day && day !== today && <button type="button" className="btn secondary small" onClick={() => go({ day: "" })}>Back to today</button>}
          </div>
        )}
      </div>
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
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          <ul aria-label="Follow-ups" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((fu) => (
              <FollowUpItem key={fu.id} followUp={fu} card leadBasePath={leadBasePath} showTelecaller={showTelecaller}
                onChanged={(_, text) => { setNotice({ text, failed: false }); reload(); }}
                onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
            ))}
          </ul>
          {data.total > LIST_LIMIT && (
            <nav aria-label="Follow-up pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - LIST_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go({}, offset + LIST_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
