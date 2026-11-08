"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
import { isPlacementListPage, isPlacementView, PLACEMENT_TABS, placementPath, placementsUrl, type PlacementItem, type PlacementListPage, PLACEMENTS_LIMIT, type PlacementView } from "@/lib/placements";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<PlacementView, string> = {
  pending: "No accepted offers are waiting to join.", joined: "No placements have joined yet.", invoice_drafts: "No invoice drafts to review.",
  did_not_join: "No placements marked Did not join.",
};

function Row({ item: i }: { item: PlacementItem }) {
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <Link href={placementPath(i.id)} style={LINK_STYLE}><strong>{i.candidate.name}</strong></Link>
        <span className="muted" style={{ fontSize: 13 }}>{i.candidate.code}</span>
        <span className="badge">{i.status_label}</span>
        {i.invoice_status_label && i.invoice_status !== "none" && <span className="badge">Invoice: {i.invoice_status_label}</span>}
      </div>
      <p style={{ margin: 0, overflowWrap: "anywhere" }}>{i.role} · {i.requirement.title} ({i.requirement.code}) · {i.company.name}</p>
      {i.joined_on && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Joined {formatCalendarDate(i.joined_on)}</p>}
    </li>
  );
}

/** pob-024: the caller's placements by joining state, plus the invoice drafts waiting for review. The tab and page live in the URL. */
export default function PlacementsPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("view");
  const view: PlacementView = isPlacementView(raw) ? raw : "pending";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = placementsUrl(view, offset);
  const [data, setData] = useState<PlacementListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<PlacementItem>(requestUrl, controller.signal)
      .then((body) => {
        if (!isPlacementListPage(body)) throw new Error("Placements without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextView: PlacementView, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextView !== "pending") next.set("view", nextView);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Placement lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {PLACEMENT_TABS.map(([key, label]) => {
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
          <p className="form-error" role="alert">Unable to load placements.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading placements…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          <ul aria-label="Placements" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>{data.items.map((item) => <Row key={item.id} item={item} />)}</ul>
          {data.total > PLACEMENTS_LIMIT && (
            <nav aria-label="Placement pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(view, Math.max(0, offset - PLACEMENTS_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(view, offset + PLACEMENTS_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
