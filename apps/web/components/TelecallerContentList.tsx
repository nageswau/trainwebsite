"use client";
import CreateJumpLink from "@/components/CreateJumpLink";
import { CATALOGUE_PAGE_SIZE } from "@/lib/telecallerCatalogue";
import type { UrlList } from "@/lib/useUrlList";

type Props<T> = {
  title: string; // "Scripts" -- also the table region's name and the loading/error/empty wording
  noun: string; // "scripts"
  list: UrlList<T>;
  notice: string | null;
  filter: React.ReactNode;
  createTargetId: string;
  createLabel: string;
  headers: string[];
  children: (items: T[]) => React.ReactNode;
};

// tel-012: the list card shared by the three library screens (the TelecallerProductsPanel layout): loading, error + Retry, empty,
// the table, and a pager. The panel owns the rows and the notice their changes report.
export default function TelecallerContentList<T>({ title, noun, list, notice, filter, createTargetId, createLabel, headers, children }: Props<T>) {
  const { data, loadFailed, reload, offset, go } = list;
  return (
    <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
      <h3>{title}</h3>
      <CreateJumpLink targetId={createTargetId} label={createLabel} />
      {filter}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8, overflowWrap: "anywhere" } : undefined}>{notice}</div>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load {noun}.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading {noun}…</p>
      ) : data.items.length === 0 ? (
        <p className="empty" role="status">{list.filter ? `No ${noun} match this filter.` : `No ${noun} yet.`}</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label={title} tabIndex={0}>
            <table>
              <thead>
                <tr>
                  {headers.map((h) => <th key={h} scope="col">{h}</th>)}
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>{children(data.items)}</tbody>
            </table>
          </div>
          {data.total > CATALOGUE_PAGE_SIZE && (
            <nav aria-label={`${title} pages`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(list.filter, Math.max(0, offset - CATALOGUE_PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(list.filter, offset + CATALOGUE_PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
