"use client";
import { type ReactNode, useRef, useState } from "react";

import BdmActivityCounts from "@/components/BdmActivityCounts";
import BdmActivityForm from "@/components/BdmActivityForm";
import BdmActivityItem from "@/components/BdmActivityItem";
import { type ActivityDayPage, DAY_PAGE, isDayPage } from "@/lib/bdmActivities";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.2, §12.2 F3/F7/F8): one IST day of activities with its counts, under the page's own title (`header`), with Log
// activity among the title's actions. After any write the day is re-read (first page) so the counts stay exact; while it re-reads,
// the old list and counts stay visible and are marked busy. "Load more" appends the next page.
export default function BdmActivityDay({
  header, initial, url, canLog, orgBasePath, emptyText = "No activities on this day.",
}: { header: ReactNode; initial: ActivityDayPage; url: string; canLog: boolean; orgBasePath: string; emptyText?: string }) {
  const [day, setDay] = useState(initial);
  const [logging, setLogging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const latest = useRef(0); // read sequence: only the newest request may change the page (older answers can arrive late)
  const sep = url.includes("?") ? "&" : "?";

  async function read(offset: number, append: boolean, text?: string) {
    const mine = ++latest.current;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(`${url}${sep}limit=${DAY_PAGE}&offset=${offset}`);
      const data = response.ok ? await response.json() : null;
      if (!isDayPage(data)) throw new Error("bad page");
      if (mine !== latest.current) return;
      setDay((current) => (append ? { ...data, items: [...current.items, ...data.items.filter((a) => !current.items.some((c) => c.id === a.id))] } : data));
      if (text) setNotice(text);
    } catch {
      if (mine === latest.current) setFailure("The day couldn't be refreshed. Reload the page to see the latest counts.");
    } finally {
      if (mine === latest.current) {
        setBusy(false);
        if (text) focus("activity-day-status"); // after a write only; "Load more" leaves focus where it is
      }
    }
  }

  return (
    <>
      <div className="portal-title">
        <div>{header}</div>
        {canLog && !logging && (
          <button id="activity-day-log" type="button" className="btn" onClick={() => setLogging(true)}>Log activity</button>
        )}
      </div>
      {logging && (
        <section className="action-card wide" aria-label="Log activity">
          <BdmActivityForm onSaved={() => { setLogging(false); void read(0, false, "Activity logged."); }} onCancel={() => { setLogging(false); focus("activity-day-log"); }} />
        </section>
      )}
      <BdmActivityCounts counts={day.counts} busy={busy} />
      <div id="activity-day-status" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {day.items.length === 0 ? (
        <p className="empty">{emptyText}</p>
      ) : (
        <ol className="jtl" aria-label="Activities" aria-busy={busy || undefined} style={{ listStyle: "none", padding: 0 }}>
          {day.items.map((a) => (
            <BdmActivityItem key={a.id} activity={a} showOrganization orgBasePath={orgBasePath}
              onChanged={() => void read(0, false, "Activity saved.")} onDeleted={() => void read(0, false, "Activity deleted.")} />
          ))}
        </ol>
      )}
      {day.items.length < day.total && (
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => void read(day.items.length, true)}>{busy ? "Loading…" : "Load more"}</button>
      )}
    </>
  );
}
