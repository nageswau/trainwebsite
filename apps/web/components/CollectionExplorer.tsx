"use client";

import type {ReactNode} from "react";
import {useMemo, useState} from "react";

export type CollectionItem = {id: string; searchText: string; filters?: Record<string, string>; sortValues?: Record<string, string | number | null | undefined>; content: ReactNode};
export type CollectionFilter = {key: string; label: string; allLabel?: string};
export type CollectionSort = {value: string; key: string; label: string; direction?: "asc" | "desc"};

function compare(left: string | number | null | undefined, right: string | number | null | undefined) {
  if (left === null || left === undefined || left === "") return 1;
  if (right === null || right === undefined || right === "") return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  const leftText = String(left); const rightText = String(right);
  const leftDate = /^\d{4}-\d{2}-\d{2}/.test(leftText) ? Date.parse(leftText) : Number.NaN;
  const rightDate = /^\d{4}-\d{2}-\d{2}/.test(rightText) ? Date.parse(rightText) : Number.NaN;
  if (!Number.isNaN(leftDate) && !Number.isNaN(rightDate)) return leftDate - rightDate;
  return leftText.localeCompare(rightText, undefined, {numeric: true, sensitivity: "base"});
}

function pageNumbers(current: number, total: number) {
  const start = Math.max(1, Math.min(current - 1, total - 2)); const end = Math.min(total, start + 2);
  return Array.from({length: Math.max(0, end - start + 1)}, (_, index) => start + index);
}

export default function CollectionExplorer({items, noun, searchPlaceholder, filters = [], sorts, empty, layoutClassName = "grid three", initialPageSize = 9}: {items: CollectionItem[]; noun: string; searchPlaceholder: string; filters?: CollectionFilter[]; sorts: CollectionSort[]; empty: ReactNode; layoutClassName?: string; initialPageSize?: number}) {
  const controlId = noun.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "collection";
  const [query, setQuery] = useState("");
  const [selectedFilters, setSelectedFilters] = useState<Record<string, string>>({});
  const [sortValue, setSortValue] = useState(sorts[0]?.value || "");
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [page, setPage] = useState(1);

  const filterChoices = useMemo(() => Object.fromEntries(filters.map(filter => [filter.key, Array.from(new Set(items.map(item => item.filters?.[filter.key]).filter((value): value is string => Boolean(value)))).sort((a, b) => a.localeCompare(b, undefined, {numeric: true, sensitivity: "base"}))])), [filters, items]);
  const shown = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase(); const selectedSort = sorts.find(sort => sort.value === sortValue) || sorts[0];
    const matching = items.filter(item => (!normalizedQuery || item.searchText.toLocaleLowerCase().includes(normalizedQuery)) && filters.every(filter => !selectedFilters[filter.key] || item.filters?.[filter.key] === selectedFilters[filter.key]));
    if (!selectedSort) return matching;
    return [...matching].sort((left, right) => {const result = compare(left.sortValues?.[selectedSort.key], right.sortValues?.[selectedSort.key]); return selectedSort.direction === "desc" ? -result : result;});
  }, [filters, items, query, selectedFilters, sortValue, sorts]);

  const totalPages = Math.max(1, Math.ceil(shown.length / pageSize)); const currentPage = Math.min(page, totalPages);
  const pageItems = shown.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const firstResult = shown.length ? (currentPage - 1) * pageSize + 1 : 0; const lastResult = Math.min(currentPage * pageSize, shown.length);
  const hasActiveFilters = Boolean(query || Object.values(selectedFilters).some(Boolean));
  function clearControls() {setQuery(""); setSelectedFilters({}); setSortValue(sorts[0]?.value || ""); setPage(1);}

  return <>
    <div className="collection-controls" aria-label={`${noun} controls`}>
      <div className="collection-search"><label htmlFor={`${controlId}-search`}>Search</label><input id={`${controlId}-search`} className="search" type="search" aria-label={`Search ${noun}`} placeholder={searchPlaceholder} value={query} onChange={event => {setQuery(event.target.value); setPage(1);}}/></div>
      {filters.map(filter => <div key={filter.key}><label htmlFor={`${controlId}-${filter.key}`}>{filter.label}</label><select id={`${controlId}-${filter.key}`} className="select" value={selectedFilters[filter.key] || ""} onChange={event => {setSelectedFilters(current => ({...current, [filter.key]: event.target.value})); setPage(1);}}><option value="">{filter.allLabel || `All ${filter.label.toLocaleLowerCase()}`}</option>{filterChoices[filter.key]?.map(value => <option key={value} value={value}>{value}</option>)}</select></div>)}
      <div><label htmlFor={`${controlId}-sort`}>Sort by</label><select id={`${controlId}-sort`} className="select" value={sortValue} onChange={event => {setSortValue(event.target.value); setPage(1);}}>{sorts.map(sort => <option key={sort.value} value={sort.value}>{sort.label}</option>)}</select></div>
      <div><label htmlFor={`${controlId}-page-size`}>Per page</label><select id={`${controlId}-page-size`} className="select" value={pageSize} onChange={event => {setPageSize(Number(event.target.value)); setPage(1);}}>{[6, 9, 18].map(size => <option key={size} value={size}>{size}</option>)}</select></div>
      {hasActiveFilters && <button className="btn ghost small" type="button" onClick={clearControls}>Clear</button>}
    </div>
    <div className="collection-summary" aria-live="polite">Showing {firstResult}–{lastResult} of {shown.length} {noun}</div>
    {pageItems.length ? <div className={layoutClassName}>{pageItems.map(item => <div className="collection-item" key={item.id}>{item.content}</div>)}</div> : <div className="collection-empty">{hasActiveFilters ? <div className="card"><h3>No matching {noun}</h3><p className="muted">Try a broader search or clear the filters.</p><button className="btn secondary small" type="button" onClick={clearControls}>Clear controls</button></div> : empty}</div>}
    {shown.length > 0 && <div className="pagination-bar collection-pagination"><p>Page {currentPage} of {totalPages}</p><nav className="pagination" aria-label={`${noun} pagination`}><button type="button" onClick={() => setPage(1)} disabled={currentPage === 1} aria-label="First page">«</button><button type="button" onClick={() => setPage(current => Math.max(1, current - 1))} disabled={currentPage === 1}>Previous</button>{pageNumbers(currentPage, totalPages).map(number => <button type="button" key={number} className={number === currentPage ? "active" : ""} aria-current={number === currentPage ? "page" : undefined} onClick={() => setPage(number)}>{number}</button>)}<button type="button" onClick={() => setPage(current => Math.min(totalPages, current + 1))} disabled={currentPage === totalPages}>Next</button><button type="button" onClick={() => setPage(totalPages)} disabled={currentPage === totalPages} aria-label="Last page">»</button></nav></div>}
  </>;
}
