"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { sendJson, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import { PAGE_SIZE, TEAM_LABEL, pageOffset, type TelecallerTeam, type TelecallerTeamRow } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";
import { ASSIGNED_URL, ASSIGN_URL, UNASSIGNED_URL, myReports, type QueueLead } from "@/lib/telecallerDistribution";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

type View = "unassigned" | "assigned";
const TEAMS: TelecallerTeam[] = ["it", "overseas"];
const TABS: { key: View; label: string }[] = [{ key: "unassigned", label: "Unassigned" }, { key: "assigned", label: "Assigned to my team" }];
const FEEDBACK_ID = "assign-feedback";

// tel-007 (DI4, D3): the manager's Lead assignment page. Two tabs -- the unassigned queue of my reports' teams (oldest first) and my
// reports' leads (newest first, filter by telecaller) -- with the view, filter, search and page in the URL. Select leads on the page,
// choose an active report and Assign / Reassign; the API re-checks scope (404), reports (403) and the team (422).
export default function TelecallerAssignmentPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view: View = params.get("view") === "assigned" ? "assigned" : "unassigned";
  const telecaller = view === "assigned" ? params.get("telecaller") ?? "" : "";
  const team = TEAMS.find((t) => t === params.get("team")) ?? ""; // QA-01: narrow a two-team list to one team
  const query = (params.get("q") ?? "").trim();
  const offset = pageOffset(params.get("offset") ?? undefined);
  const [draft, setDraft] = useState(query);
  useEffect(() => setDraft(query), [query]);
  const [data, setData] = useState<Page<QueueLead> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reports, setReports] = useState<TelecallerTeamRow[] | null>(null);
  const [reportsFailed, setReportsFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const inFlight = useRef(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const focus = useFocusAfterRender();

  function go(next: { view?: View; telecaller?: string; team?: string; q?: string; offset?: number }) {
    const state = { view, telecaller, team, q: query, offset, ...next };
    const search = new URLSearchParams();
    if (state.view === "assigned") search.set("view", "assigned");
    if (state.view === "assigned" && state.telecaller) search.set("telecaller", state.telecaller);
    if (state.team) search.set("team", state.team);
    if (state.q) search.set("q", state.q);
    if (state.offset > 0) search.set("offset", String(state.offset));
    router.push(search.size ? `${pathname}?${search}` : pathname, { scroll: false });
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    setData(null);
    setSelected(new Set());
    const request = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) request.set("q", query);
    if (telecaller) request.set("telecaller_user_id", telecaller);
    if (team) request.set("team", team);
    getPage<QueueLead>(`${view === "assigned" ? ASSIGNED_URL : UNASSIGNED_URL}?${request}`, controller.signal)
      .then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [view, telecaller, team, query, offset, version]);

  const loadReports = useCallback(() => {
    setReportsFailed(false);
    myReports().then(setReports).catch(() => setReportsFailed(true));
  }, []);
  useEffect(() => loadReports(), [loadReports]);

  const items = data?.items ?? [];
  const active = (reports ?? []).filter((r) => r.active);
  const allSelected = items.length > 0 && items.every((x) => selected.has(x.id));
  const verb = view === "assigned" ? "Reassign" : "Assign";
  const toggle = (leadId: string) => setSelected((s) => {
    const next = new Set(s);
    if (!next.delete(leadId)) next.add(leadId);
    return next;
  });

  function fail(text: string) {
    setFeedback({ text, tone: "error" });
    focus(FEEDBACK_ID);
  }

  async function assign() {
    if (inFlight.current) return;
    const chosen = active.find((r) => r.id === target);
    if (!chosen) return fail("Choose a telecaller.");
    const leads = items.filter((x) => selected.has(x.id));
    const teams = new Set(leads.map((x) => x.division));
    if (teams.size > 1) return fail("Choose leads from one team.");
    if (!teams.has(chosen.team)) return fail(`${chosen.full_name} is on the ${TEAM_LABEL[chosen.team]} team; choose leads from that team.`);
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(ASSIGN_URL, "POST", { lead_ids: leads.map((x) => x.id), telecaller_user_id: chosen.id });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message);
    const { assigned, unchanged } = outcome.data as { assigned: number; unchanged: number };
    const moved = `${verb}ed ${assigned} lead${assigned === 1 ? "" : "s"} to ${chosen.full_name}`;
    setFeedback({ text: unchanged ? `${moved}; ${unchanged} already with them.` : `${moved}.`, tone: "success" });
    focus(FEEDBACK_ID);
    setVersion((v) => v + 1);
  }

  // QA-02: the empty state names the active filter, never claims the whole team has no leads.
  function emptyText() {
    if (query) return `No leads match “${query}”.`;
    const onTeam = team ? ` on the ${TEAM_LABEL[team]} team` : "";
    if (view === "unassigned") return team ? `No unassigned leads${onTeam}.` : "No unassigned leads. New leads with no matching rule or available telecaller appear here.";
    const person = reports?.find((r) => r.id === telecaller)?.full_name;
    if (telecaller) return `No leads are assigned to ${person ?? "this telecaller"}${onTeam}.`;
    return `No leads are assigned to your telecallers${onTeam} yet.`;
  }

  function onTabKey(event: React.KeyboardEvent, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const next = (index + (event.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    tabRefs.current[next]?.focus();
    go({ view: TABS[next].key, telecaller: "", offset: 0 });
  }

  return (
    <div className="action-card wide telecaller-list">
      <div role="tablist" aria-label="Leads" className="report-tablist">
        {TABS.map((t, i) => (
          <button
            key={t.key} ref={(el) => { tabRefs.current[i] = el; }} id={`assign-tab-${t.key}`} type="button" role="tab" className="s360-tab"
            aria-selected={t.key === view} aria-controls="assign-panel" tabIndex={t.key === view ? 0 : -1}
            onClick={() => go({ view: t.key, telecaller: "", offset: 0 })} onKeyDown={(e) => onTabKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="assign-panel" role="tabpanel" aria-labelledby={`assign-tab-${view}`} aria-busy={data === null && !loadFailed}>
        <p className="muted" style={{ fontSize: 13 }}>
          {view === "unassigned"
            ? "Leads no rule or available telecaller could take, oldest first. Assign them to someone on their team."
            : "Leads of the telecallers who report to you, newest first. Reassigning keeps the lead's stage."}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="assign-team">Team</label>
            <select id="assign-team" value={team} onChange={(e) => go({ team: e.target.value, offset: 0 })}>
              <option value="">Both teams</option>
              {TEAMS.map((t) => <option key={t} value={t}>{TEAM_LABEL[t]}</option>)}
            </select>
          </div>
          {view === "assigned" && (
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="assign-filter">Telecaller</label>
              <select id="assign-filter" value={telecaller} onChange={(e) => go({ telecaller: e.target.value, offset: 0 })}>
                <option value="">All my telecallers</option>
                {(reports ?? []).map((r) => <option key={r.id} value={r.id}>{r.full_name}{r.active ? "" : " (inactive)"}</option>)}
              </select>
            </div>
          )}
          <form role="search" onSubmit={(event) => { event.preventDefault(); go({ q: draft.trim(), offset: 0 }); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", flex: "1 1 260px" }}>
            <input type="search" aria-label="Search leads" placeholder="Lead ID, name or city" value={draft} maxLength={200} onChange={(e) => setDraft(e.target.value)} style={{ flex: "1 1 200px" }} />
            <button type="submit" className="btn secondary small">Search</button>
            {query && <button type="button" className="btn secondary small" onClick={() => go({ q: "", offset: 0 })}>Clear search</button>}
          </form>
        </div>
        <div role="group" aria-label={`${verb} selected leads`} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="assign-target">Assign to</label>
            <select id="assign-target" value={target} onChange={(e) => setTarget(e.target.value)} disabled={busy || !active.length}>
              <option value="">{reports === null && !reportsFailed ? "Loading telecallers…" : "Choose a telecaller"}</option>
              {active.map((r) => <option key={r.id} value={r.id}>{r.full_name} ({TEAM_LABEL[r.team]})</option>)}
            </select>
          </div>
          <button type="button" className="btn" onClick={assign} disabled={busy || selected.size === 0}>
            {busy ? `${verb}ing…` : selected.size ? `${verb} ${selected.size} selected` : `${verb} selected`}
          </button>
        </div>
        {reportsFailed && (
          <p className="form-error" role="alert">Unable to load your telecallers. <button type="button" className="btn secondary small" onClick={loadReports}>Retry loading telecallers</button></p>
        )}
        {reports !== null && !active.length && <p className="muted" style={{ fontSize: 13 }}>No active telecaller reports to you, so leads can&apos;t be assigned from here.</p>}
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load leads.</p>
            <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading leads…</p>
        ) : items.length === 0 ? (
          <p className="empty" role="status">
            {emptyText()}
          </p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Leads" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col"><input type="checkbox" aria-label="Select all leads on this page" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((x) => x.id)))} disabled={busy} /></th>
                    <th scope="col">Lead ID</th><th scope="col">Name</th><th scope="col">Team</th><th scope="col">City</th><th scope="col">Product</th>
                    <th scope="col">Stage</th>{view === "assigned" && <th scope="col">Telecaller</th>}<th scope="col">Received</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((x) => (
                    <tr key={x.id}>
                      <td><input type="checkbox" aria-label={`Select ${x.name}`} checked={selected.has(x.id)} onChange={() => toggle(x.id)} disabled={busy} /></td>
                      <td data-label="Lead ID">{x.lead_code}</td>
                      <td data-label="Name">{x.name}</td>
                      <td data-label="Team">{TEAM_LABEL[x.division] ?? x.division}</td>
                      <td data-label="City">{x.city ?? "—"}</td>
                      <td data-label="Product">{x.product?.name ?? "—"}</td>
                      <td data-label="Stage">{x.status_label}</td>
                      {view === "assigned" && <td data-label="Telecaller">{x.telecaller?.full_name}{x.telecaller && !x.telecaller.active && <> <span className="badge">Inactive</span></>}</td>}
                      <td data-label="Received">{formatDate(x.created_at, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="Lead pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go({ offset: Math.max(0, offset - PAGE_SIZE) })}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + items.length >= data.total} onClick={() => go({ offset: offset + PAGE_SIZE })}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  );
}
