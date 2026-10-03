"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { Page } from "@/lib/apiErrors";
import { isPage } from "@/lib/apiErrors";
import { NETWORK_PATH, ORG_STATUS_LABEL, ORGS_URL, PAGE_SIZE, statusClass, failureText, type NetworkOrg, type OrgStatus } from "@/lib/agentNetwork";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-022 (DEC-SCOPE-063): every agency on EduSphere with its people and pipeline, for Overseas and Super Admins. Read-only here:
// suspend/reinstate live on the agency's detail page, approve/reject on Agent Approvals. Tab, page and search live in the URL (as
// AgentApprovalPanel). While a page loads the previous one stays on screen, dimmed; a slower older response is dropped.
type Tab = "all" | OrgStatus;
const TABS: { value: Tab; label: string; empty: string }[] = [
  { value: "all", label: "All", empty: "No agencies yet." },
  { value: "active", label: "Active", empty: "No active agencies." },
  { value: "suspended", label: "Suspended", empty: "No suspended agencies." },
  { value: "pending", label: "Pending", empty: "No pending agencies." },
  { value: "rejected", label: "Rejected", empty: "No rejected agencies." },
];
const RESULTS_ID = "agent-network-results";
type Loaded = { page: Page<NetworkOrg>; tab: Tab; query: string };

export default function AgentNetworkPanel() {
  const [tab, setTab] = useState<Tab>("all");
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [ready, setReady] = useState(false);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const seq = useRef(0);
  const focusResults = useRef(false);
  const focus = useFocusAfterRender();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = TABS.find((t) => t.value === params.get("tab"));
    if (fromUrl) setTab(fromUrl.value);
    const pageNumber = Number.parseInt(params.get("page") ?? "1", 10);
    if (Number.isFinite(pageNumber) && pageNumber > 1) setOffset((pageNumber - 1) * PAGE_SIZE);
    const searched = (params.get("q") ?? "").trim().slice(0, 100);
    setQuery(searched);
    setDraft(searched);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    ["tab", "page", "q"].forEach((key) => params.delete(key));
    if (tab !== "all") params.set("tab", tab);
    if (offset > 0) params.set("page", String(offset / PAGE_SIZE + 1));
    if (query) params.set("q", query);
    const search = params.toString();
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`);
  }, [ready, tab, offset, query]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (tab !== "all") params.set("status", tab);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    if (query) params.set("q", query);
    try {
      const res = await fetch(`${ORGS_URL}?${params}`);
      const failure = res.ok ? null : await failureText(res, "Unable to load agencies.");
      const body = res.ok ? await res.json().catch(() => null) : null;
      if (mine !== seq.current) return; // a newer request owns the screen
      if (failure || !isPage<NetworkOrg>(body)) {
        setError(failure ?? "Unable to load agencies.");
        return;
      }
      setLoaded({ page: body, tab, query });
      if (focusResults.current) {
        focusResults.current = false;
        focus(RESULTS_ID);
      }
    } catch {
      if (mine === seq.current) setError("Network error. Check your connection and try again.");
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [tab, offset, query, focus]);

  useEffect(() => {
    if (ready) void load();
  }, [ready, load, retry]);

  function showTab(value: Tab) {
    focusResults.current = true;
    setTab(value);
    setOffset(0);
  }

  function goTo(nextOffset: number) {
    focusResults.current = true;
    setOffset(nextOffset);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    focusResults.current = true;
    setQuery(draft.trim().slice(0, 100));
    setOffset(0);
  }

  const current = TABS.find((t) => t.value === tab) ?? TABS[0];
  const shown = loaded ? (TABS.find((t) => t.value === loaded.tab) ?? TABS[0]) : current;
  const data = loaded?.page;

  return (
    <div className="action-card agent-network">
      <div>
        <h2>Agent network</h2>
        <p className="muted">Every agency on EduSphere, with its people and pipeline. Open an agency to see its students and applications, or to suspend it.</p>
      </div>
      <div role="group" aria-label="Agency status" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {TABS.map((t) => (
          <button key={t.value} type="button" className={t.value === tab ? "btn small" : "btn secondary small"} aria-pressed={t.value === tab} onClick={() => showTab(t.value)}>
            {t.label}
          </button>
        ))}
      </div>
      <form role="search" onSubmit={search} style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8 }}>
        <div className="field" style={{ flex: "1 1 220px", margin: 0 }}>
          <label htmlFor="agent-network-search">Search agencies</label>
          <input id="agent-network-search" type="search" value={draft} maxLength={100} placeholder="Agency, prefix, code or Master email" onChange={(e) => setDraft(e.target.value)} />
        </div>
        <button type="submit" className="btn secondary small">
          Search
        </button>
      </form>
      {/* The table's scroll region carries the heading's name, so the section stays unnamed (one landmark, not two -- QA18-06). */}
      <section>
        <h3 id={RESULTS_ID} tabIndex={-1}>
          {current.label} agencies
        </h3>
        {error ? (
          <>
            <p className="form-error" role="alert">
              {error}
            </p>
            <button type="button" className="btn secondary small" onClick={() => setRetry((n) => n + 1)}>
              Retry
            </button>
          </>
        ) : !data ? (
          <p className="muted" role="status">
            Loading agencies…
          </p>
        ) : data.items.length === 0 ? (
          <p className="muted" aria-busy={loading}>
            {loaded.query ? `No agencies match “${loaded.query}”.` : shown.empty}
          </p>
        ) : (
          <>
            <div className="table-scroll" role="region" aria-labelledby={RESULTS_ID} tabIndex={0} aria-busy={loading} style={{ opacity: loading ? 0.6 : 1 }}>
              <table className="table compact stack">
                <thead>
                  <tr>
                    {["Agency", "Status", "Masters", "Staff", "Students", "Applications", "Enrollments"].map((h) => (
                      <th scope="col" key={h}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((org) => (
                    <tr key={org.id}>
                      <th scope="row" style={{ overflowWrap: "anywhere" }}>
                        <Link href={`${NETWORK_PATH}/${encodeURIComponent(org.id)}`}>
                          {org.name} <span className="muted">({org.prefix})</span>
                        </Link>
                      </th>
                      <td data-label="Status">
                        <span className={statusClass(org.status)}>{ORG_STATUS_LABEL[org.status] ?? org.status}</span>
                      </td>
                      <td data-label="Masters">
                        {org.masters.map((m) => (
                          <span key={m.id} style={{ display: "block" }}>
                            {m.code}
                          </span>
                        ))}
                      </td>
                      <td data-label="Staff">{org.staff_count}</td>
                      <td data-label="Students">{org.counts.students}</td>
                      <td data-label="Applications">{org.counts.applications}</td>
                      <td data-label="Enrollments">{org.counts.enrollments}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav aria-label="Agency pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={loading || data.offset === 0} onClick={() => goTo(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={loading || data.offset + data.items.length >= data.total} onClick={() => goTo(offset + PAGE_SIZE)}>
                Next
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  );
}
