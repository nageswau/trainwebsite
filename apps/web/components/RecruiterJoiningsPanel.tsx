"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { isJoiningListPage, isJoiningView, JOINING_TABS, joiningsUrl, type JoiningItem, type JoiningListPage, JOININGS_LIMIT, type JoiningView } from "@/lib/recruiterOffers";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<JoiningView, string> = {
  due: "No joinings are due.", joined: "No candidates have joined yet.", did_not_join: "No candidates marked Did Not Join.",
};

function Row({ item: i }: { item: JoiningItem }) {
  const j = i.joining;
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong>{i.candidate.name}</strong>
        <span className="muted" style={{ fontSize: 13 }}>{i.candidate.code}</span>
        <span className="badge">{j.status_label}</span>
        {j.overdue && <span className="badge status error">Overdue</span>}
      </div>
      <p style={{ margin: 0, overflowWrap: "anywhere" }}>
        <Link href={`/recruiter/requirements/${encodeURIComponent(i.requirement.id)}`} style={LINK_STYLE}>{i.requirement.title} ({i.requirement.code})</Link>
        {" · "}{i.company.name}{i.position ? ` · ${i.position}` : ""}
      </p>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Expected {j.expected_joining_date ? formatCalendarDate(j.expected_joining_date) : "not set"}
        {j.actual_joining_date && ` · Joined ${formatCalendarDate(j.actual_joining_date)}`}
        {j.location && ` · ${j.location}`}
      </p>
      {j.reason && <p style={{ margin: 0, fontSize: 13, overflowWrap: "anywhere" }}>Reason: {j.reason}</p>}
    </li>
  );
}

/** rec-023 (spec §4): the caller's joinings -- Joining due (soonest expected date first, overdue flagged), Joined and Did not join. The
 *  tab and page live in the URL, so refresh keeps the place. The API scopes the rows; the joining is updated on the candidate's offer. */
export default function RecruiterJoiningsPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("view");
  const view: JoiningView = isJoiningView(raw) ? raw : "due";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = joiningsUrl(view, offset);
  const [data, setData] = useState<JoiningListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<JoiningItem>(requestUrl, controller.signal)
      .then((body) => {
        if (!isJoiningListPage(body)) throw new Error("Joinings without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextView: JoiningView, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextView !== "due") next.set("view", nextView);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Joining lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {JOINING_TABS.map(([key, label]) => {
          const n = data?.counts[key];
          return (
            <button key={key} type="button" aria-current={view === key ? "page" : undefined} className={`btn small${view === key ? "" : " secondary"}`} onClick={() => go(key)}>
              {label}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      {failed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load joinings.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading joinings…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          <ul aria-label="Joinings" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>{data.items.map((item) => <Row key={item.id} item={item} />)}</ul>
          {data.total > JOININGS_LIMIT && (
            <nav aria-label="Joining pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(view, Math.max(0, offset - JOININGS_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(view, offset + JOININGS_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
