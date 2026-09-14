"use client";

import {FormEvent, useState} from "react";
import Link from "next/link";
import CollectionExplorer from "./CollectionExplorer";

type SearchRow = {title: string; href: string};
type SearchData = {programs?: SearchRow[]; universities?: SearchRow[]; articles?: SearchRow[]};

export default function SearchClient() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<SearchData | null>(null);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) { setError("Enter at least two characters."); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/v1/public/search?q=${encodeURIComponent(query.trim())}`);
      if (!response.ok) throw new Error("Search is temporarily unavailable.");
      setData(await response.json());
    } catch (reason) { setData(null); setError(reason instanceof Error ? reason.message : "Search is temporarily unavailable."); }
    finally { setBusy(false); }
  }

  const typedRows = data ? [
    ...(data.programs || []).map(row => ({...row, type: "IT Programs"})),
    ...(data.universities || []).map(row => ({...row, type: "Universities"})),
    ...(data.articles || []).map(row => ({...row, type: "News & Articles"})),
  ] : [];
  const items = typedRows.map((row, index) => ({
    id: `${row.type}-${row.href}-${index}`, searchText: `${row.title} ${row.type}`, filters: {type: row.type}, sortValues: {title: row.title, type: row.type},
    content: <Link className="card hover" href={row.href}><span className="badge">{row.type}</span><h3 style={{marginTop: 12}}>{row.title}</h3><span className="muted">Open result →</span></Link>,
  }));

  return <>
    <form className="filterbar" onSubmit={submit}><input className="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search programs, universities and articles…" aria-label="Search EduSphere"/><button className="btn" disabled={busy}>{busy ? "Searching…" : "Search"}</button></form>
    {error && <p className="form-error" role="alert">{error}</p>}
    {data && <CollectionExplorer items={items} noun="search results" searchPlaceholder="Refine these results…" filters={[{key: "type", label: "Result type"}]} sorts={[{value: "title", key: "title", label: "Title A–Z"}, {value: "title-desc", key: "title", label: "Title Z–A", direction: "desc"}, {value: "type", key: "type", label: "Result type"}]} initialPageSize={6} empty={<div className="card"><h3>No results found</h3><p className="muted">Try a different search phrase.</p></div>}/>} 
  </>;
}
