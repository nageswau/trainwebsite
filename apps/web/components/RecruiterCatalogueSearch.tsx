"use client";
import { useEffect, useState } from "react";

import type { UrlList } from "@/lib/useUrlList";

// rec-002: the name search above a recruiter catalogue list. The text lives in the URL (?q=, via useUrlList), so refresh keeps it and
// Back returns to the previous search; a new search starts at the first page.
export default function RecruiterCatalogueSearch<T>({ list, label }: { list: UrlList<T>; label: string }) {
  const [draft, setDraft] = useState(list.filter);
  useEffect(() => setDraft(list.filter), [list.filter]);
  const search = (text: string) => {
    setDraft(text);
    list.go(text.trim(), 0);
  };
  return (
    <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <input type="search" aria-label={label} placeholder="Name" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
      <button type="submit" className="btn secondary small">Search</button>
      {list.filter && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
    </form>
  );
}
