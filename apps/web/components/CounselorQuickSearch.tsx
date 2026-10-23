"use client";

import Link from "next/link";
import { useId, useRef, useState } from "react";

import { detailMessage } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

export const COUNSELOR_SEARCH_URL = "/api/v1/counselor/search";
const MIN_CHARS = 3;

type Hit = { id: string; code: string | null; label: string | null; detail: string | null; href: string };
type Group = { items: Hit[]; more: boolean };
export type SearchResult = { q: string; leads: Group; students: Group; applications: Group };

const GROUPS = [
  ["leads", "Leads"],
  ["students", "Students"],
  ["applications", "Applications"],
] as const;

/** ccrm-012 (DEC-SCOPE-246 QS1-QS5): one box across the counselor's own leads, students and applications -- name, phone, email or ID.
 *  It searches on submit (not per keystroke), so the server's 30-a-minute budget is never spent while typing. */
export default function CounselorQuickSearch() {
  const idp = useId();
  const [q, setQ] = useState("");
  const [state, setState] = useState<{ status: "idle" | "loading" } | { status: "error"; message: string } | { status: "done"; result: SearchResult }>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const term = q.trim();
    if (term.length < MIN_CHARS) {
      setState({ status: "error", message: `Type at least ${MIN_CHARS} characters` });
      return;
    }
    controller.current?.abort();
    const ctl = (controller.current = new AbortController());
    setState({ status: "loading" });
    try {
      const response = await fetch(`${COUNSELOR_SEARCH_URL}?${new URLSearchParams({ q: term })}`, { signal: ctl.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok) setState({ status: "error", message: detailMessage(data?.detail, `Search failed (${response.status})`) });
      else setState({ status: "done", result: data as SearchResult });
    } catch {
      if (!ctl.signal.aborted) setState({ status: "error", message: "Search did not complete. Check your connection and try again." });
    }
  }

  let body: React.ReactNode = null;
  if (state.status === "loading") body = <p className="muted" role="status">Searching…</p>;
  else if (state.status === "error") body = <p className="form-error" role="alert">{state.message}</p>;
  else if (state.status === "done") {
    const { result } = state;
    const total = GROUPS.reduce((n, [key]) => n + result[key].items.length, 0);
    body =
      total === 0 ? (
        <p className="muted" role="status">Nothing in your leads, students or applications matches “{result.q}”.</p>
      ) : (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }} aria-live="polite">
          {GROUPS.map(([key, title]) => (
            <section key={key} aria-labelledby={`${idp}-${key}`}>
              <h3 id={`${idp}-${key}`} style={{ fontSize: 15, margin: "0 0 6px" }}>{title} ({result[key].items.length}{result[key].more ? "+" : ""})</h3>
              {result[key].items.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>No matches</p>
              ) : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
                  {result[key].items.map((hit) => (
                    <li key={hit.id}>
                      <Link href={hit.href} style={LINK_STYLE}>{hit.label || hit.code || "Untitled"}</Link>
                      <div className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>{[hit.code, hit.detail].filter(Boolean).join(" · ")}</div>
                    </li>
                  ))}
                </ul>
              )}
              {result[key].more && <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>Showing the first 10 -- refine your search.</p>}
            </section>
          ))}
        </div>
      );
  }

  return (
    <section aria-labelledby={`${idp}-heading`} className="card" style={{ display: "grid", gap: 12, marginBottom: 16 }}>
      <h2 id={`${idp}-heading`} style={{ fontSize: 18, margin: 0 }}>Quick search</h2>
      <form role="search" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
        <div className="field" style={{ flex: "1 1 260px", margin: 0 }}>
          <label htmlFor={`${idp}-q`}>Name, phone, email or ID</label>
          <input id={`${idp}-q`} type="search" value={q} maxLength={100} onChange={(event) => setQ(event.target.value)} placeholder="e.g. APP-000012, 98765 43210" />
        </div>
        <button type="submit" className="btn" disabled={state.status === "loading"}>Search</button>
      </form>
      {body}
    </section>
  );
}
