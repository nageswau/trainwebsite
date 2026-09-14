"use client";

import {useMemo, useState} from "react";
import JoinSessionButton from "./JoinSessionButton";

type Column = {key: string; label: string; type?: string};
type Row = Record<string, unknown>;
type SortDirection = "asc" | "desc";

// `type: "join"` columns (server-declared, see `_payload()`) render a real join button
// instead of stringifying the raw URL -- `PENDING_ZOHO_LIVE_CLASSES.md` §6's own proposed
// fix, ported in per §1b item (a). No identity confirmation here (unlike
// `LiveClassesPanel`'s own use of the same button) since every page currently using this
// column type is a trainer/admin oversight table, not a student join surface.
function renderCell(column: Column, row: Row) {
  if (column.type === "join") {
    return (
      <JoinSessionButton
        joinUrl={row[column.key] as string | null}
        startsAt={String(row.starts_at ?? row.starts ?? "")}
        endsAt={row.ends_at as string | null}
        isHost={Boolean(row.host_url)}
        label="Join"
        className="btn small secondary"
      />
    );
  }
  return displayValue(row[column.key]);
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function compareValues(left: unknown, right: unknown) {
  if (left === null || left === undefined || left === "") return 1;
  if (right === null || right === undefined || right === "") return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  if (typeof left === "boolean" && typeof right === "boolean") return Number(left) - Number(right);
  const leftText = String(left);
  const rightText = String(right);
  const isoDate = /^\d{4}-\d{2}-\d{2}(?:[T\s]|$)/;
  if (isoDate.test(leftText) && isoDate.test(rightText)) {
    const leftTime = Date.parse(leftText);
    const rightTime = Date.parse(rightText);
    if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime)) return leftTime - rightTime;
  }
  return leftText.localeCompare(rightText, undefined, {numeric: true, sensitivity: "base"});
}

function pageNumbers(current: number, total: number) {
  const start = Math.max(1, Math.min(current - 1, total - 2));
  const end = Math.min(total, start + 2);
  return Array.from({length: Math.max(0, end - start + 1)}, (_, index) => start + index);
}

export default function DataTable({columns, rows, label}: {columns: Column[]; rows: Row[]; label: string}) {
  const [query, setQuery] = useState("");
  const [filterKey, setFilterKey] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [sortKey, setSortKey] = useState("");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);

  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const normalizedFilter = filterValue.trim().toLocaleLowerCase();
    return rows.filter(row => {
      const matchesSearch = !normalizedQuery || columns.some(column => displayValue(row[column.key]).toLocaleLowerCase().includes(normalizedQuery));
      const matchesFilter = !filterKey || !normalizedFilter || displayValue(row[filterKey]).toLocaleLowerCase().includes(normalizedFilter);
      return matchesSearch && matchesFilter;
    });
  }, [columns, filterKey, filterValue, query, rows]);

  const sortedRows = useMemo(() => !sortKey ? filteredRows : [...filteredRows].sort((left, right) => {
    const comparison = compareValues(left[sortKey], right[sortKey]);
    return sortDirection === "asc" ? comparison : -comparison;
  }), [filteredRows, sortDirection, sortKey]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = sortedRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const firstResult = sortedRows.length ? (currentPage - 1) * pageSize + 1 : 0;
  const lastResult = Math.min(currentPage * pageSize, sortedRows.length);

  function changeSort(key: string) {
    if (sortKey === key) setSortDirection(direction => direction === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDirection("asc"); }
    setPage(1);
  }

  function clearControls() {
    setQuery(""); setFilterKey(""); setFilterValue("");
    setSortKey(""); setSortDirection("asc"); setPage(1);
  }

  return <>
    <div className="table-controls" aria-label={`${label} table controls`}>
      <div className="table-control-search"><label htmlFor="table-search">Search records</label><input id="table-search" className="search" type="search" placeholder="Search all columns…" value={query} onChange={event => {setQuery(event.target.value); setPage(1);}}/></div>
      <div><label htmlFor="table-filter-column">Filter by</label><select id="table-filter-column" className="select" value={filterKey} onChange={event => {setFilterKey(event.target.value); setFilterValue(""); setPage(1);}}><option value="">Any column</option>{columns.map(column => <option key={column.key} value={column.key}>{column.label}</option>)}</select></div>
      <div><label htmlFor="table-filter-value">Filter value</label><input id="table-filter-value" className="search" type="search" disabled={!filterKey} placeholder={filterKey ? "Contains…" : "Choose a column"} value={filterValue} onChange={event => {setFilterValue(event.target.value); setPage(1);}}/></div>
      <div><label htmlFor="table-page-size">Rows per page</label><select id="table-page-size" className="select" value={pageSize} onChange={event => {setPageSize(Number(event.target.value)); setPage(1);}}>{[10, 25, 50].map(size => <option key={size} value={size}>{size}</option>)}</select></div>
      {(query || filterKey || filterValue) && <button className="btn ghost small" type="button" onClick={clearControls}>Clear</button>}
    </div>
    {sortedRows.length ? <>
      <div className="table-wrap"><table className="table"><thead><tr>{columns.map(column => <th key={column.key} aria-sort={sortKey === column.key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button className="sort-button" type="button" onClick={() => changeSort(column.key)}>{column.label}<span aria-hidden="true">{sortKey === column.key ? (sortDirection === "asc" ? " ↑" : " ↓") : " ↕"}</span></button></th>)}</tr></thead><tbody>{pageRows.map((row, rowIndex) => <tr key={String(row.id ?? row.reference ?? `${currentPage}-${rowIndex}`)}>{columns.map(column => <td key={column.key}>{renderCell(column, row)}</td>)}</tr>)}</tbody></table></div>
      <div className="pagination-bar"><p aria-live="polite">Showing {firstResult}–{lastResult} of {sortedRows.length} records</p><nav className="pagination" aria-label={`${label} pagination`}><button type="button" onClick={() => setPage(1)} disabled={currentPage === 1} aria-label="First page">«</button><button type="button" onClick={() => setPage(current => Math.max(1, current - 1))} disabled={currentPage === 1}>Previous</button>{pageNumbers(currentPage, totalPages).map(number => <button type="button" key={number} className={number === currentPage ? "active" : ""} aria-current={number === currentPage ? "page" : undefined} onClick={() => setPage(number)}>{number}</button>)}<button type="button" onClick={() => setPage(current => Math.min(totalPages, current + 1))} disabled={currentPage === totalPages}>Next</button><button type="button" onClick={() => setPage(totalPages)} disabled={currentPage === totalPages} aria-label="Last page">»</button></nav></div>
    </> : <div className="empty"><h3>No matching records</h3><p>Change or clear the search and filter values to see more records.</p><button className="btn secondary small" type="button" onClick={clearControls}>Clear controls</button></div>}
  </>;
}
