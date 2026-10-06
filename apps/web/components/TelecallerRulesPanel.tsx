"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import CreateJumpLink from "@/components/CreateJumpLink";
import TelecallerRuleRow from "@/components/TelecallerRuleRow";
import { sendJson, type Page } from "@/lib/apiErrors";
import { TEAM_LABEL, pageOffset, type TelecallerTeam, type TelecallerTeamRow } from "@/lib/telecaller";
import { CATALOGUE_PAGE_SIZE, activeProducts, getPage, type Product } from "@/lib/telecallerCatalogue";
import { RULES_URL, assignTargets, myReports, ruleMatch, type Rule } from "@/lib/telecallerDistribution";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "rule-create-feedback";
const TEAMS: TelecallerTeam[] = ["it", "overseas"];

// tel-007 (T11, DI3): the manager's distribution rules. A create form (team, product or city, an active report on that team) and the
// list (team filter in the URL, loading / error+Retry / empty / pager). Every manager sees every rule; only rules for their own reports
// can be changed or deleted -- the API decides.
export default function TelecallerRulesPanel() {
  const [data, setData] = useState<Page<Rule> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reports, setReports] = useState<TelecallerTeamRow[] | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [pickersFailed, setPickersFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [team, setTeam] = useState<TelecallerTeam>("it");
  const [kind, setKind] = useState<"product" | "city">("product");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filter = params.get("team") === "it" || params.get("team") === "overseas" ? (params.get("team") as TelecallerTeam) : null;
  const offset = pageOffset(params.get("offset") ?? undefined);
  function go(nextTeam: TelecallerTeam | null, nextOffset: number) {
    const next = new URLSearchParams();
    if (nextTeam) next.set("team", nextTeam);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    const request = new URLSearchParams({ limit: String(CATALOGUE_PAGE_SIZE), offset: String(offset) });
    if (filter) request.set("team", filter);
    getPage<Rule>(`${RULES_URL}?${request}`, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [filter, offset, version]);

  const loadPickers = useCallback(() => {
    setPickersFailed(false);
    Promise.all([myReports(), activeProducts()]).then(([r, p]) => { setReports(r); setProducts(p); }).catch(() => setPickersFailed(true));
  }, []);
  useEffect(() => loadPickers(), [loadPickers]);

  const reload = () => setVersion((v) => v + 1);
  const targets = reports ? assignTargets(reports, team) : [];
  const teamProducts = (products ?? []).filter((p) => p.team === team);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const telecaller = String(form.get("telecaller_user_id") ?? "");
    const body = kind === "product"
      ? { team, kind, product_id: String(form.get("product_id") ?? ""), telecaller_user_id: telecaller }
      : { team, kind, city: String(form.get("city") ?? "").trim(), telecaller_user_id: telecaller };
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(RULES_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${ruleMatch(outcome.data as Rule)}.`, tone: "success" });
      formEl.reset();
      setTeam("it");
      setKind("product");
      reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  const loadingPickers = reports === null && !pickersFailed;
  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create rule</h3>
        <div className="field">
          <label htmlFor="rule-team">Team (required)</label>
          <select id="rule-team" value={team} onChange={(e) => setTeam(e.target.value as TelecallerTeam)} disabled={busy}>
            {TEAMS.map((t) => <option key={t} value={t}>{TEAM_LABEL[t]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rule-kind">Rule type (required)</label>
          <select id="rule-kind" value={kind} onChange={(e) => setKind(e.target.value as "product" | "city")} disabled={busy}>
            <option value="product">Product</option>
            <option value="city">City</option>
          </select>
        </div>
        {kind === "product" ? (
          <div className="field">
            <label htmlFor="rule-product">Product (required)</label>
            <select key={team} id="rule-product" name="product_id" required defaultValue="" disabled={busy || !teamProducts.length}>
              <option value="" disabled>{products === null && !pickersFailed ? "Loading products…" : "Choose a product"}</option>
              {teamProducts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        ) : (
          <div className="field"><label htmlFor="rule-city">City (required)</label><input id="rule-city" name="city" required maxLength={120} placeholder="e.g. Hyderabad" disabled={busy} /></div>
        )}
        <div className="field">
          <label htmlFor="rule-telecaller">Telecaller (required)</label>
          <select key={team} id="rule-telecaller" name="telecaller_user_id" required defaultValue="" disabled={busy || !targets.length}>
            <option value="" disabled>{loadingPickers ? "Loading telecallers…" : "Choose a telecaller"}</option>
            {targets.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
          </select>
        </div>
        {reports !== null && !targets.length && <p className="muted" style={{ fontSize: 13 }}>No active telecaller on the {TEAM_LABEL[team]} team reports to you.</p>}
        {pickersFailed && (
          <p className="form-error" role="alert">
            Unable to load telecallers and products. <button type="button" className="btn secondary small" onClick={loadPickers}>Retry loading</button>
          </p>
        )}
        <button className="btn" disabled={busy || !targets.length}>{busy ? "Creating…" : "Create rule"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Rules</h3>
        <p className="muted" style={{ fontSize: 13 }}>
          A new lead goes to the telecaller of its product rule, else of its city rule, else to the next active telecaller of its team in turn.
          If nobody is available it waits in the unassigned queue. A rule whose telecaller is inactive is skipped.
        </p>
        <CreateJumpLink targetId="rule-team" label="Create rule" />
        <div className="field" style={{ maxWidth: 240 }}>
          <label htmlFor="rule-filter">Show</label>
          <select id="rule-filter" value={filter ?? ""} onChange={(e) => go((e.target.value || null) as TelecallerTeam | null, 0)}>
            <option value="">Both teams</option>
            {TEAMS.map((t) => <option key={t} value={t}>{TEAM_LABEL[t]} team</option>)}
          </select>
        </div>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load rules.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading rules…</p>
        ) : data.items.length === 0 ? (
          <p className="empty" role="status">{filter ? `No rules for the ${TEAM_LABEL[filter]} team.` : "No rules yet. Every new lead goes round robin until you add one."}</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Rules" tabIndex={0}>
              <table>
                <thead>
                  <tr><th scope="col">Rule</th><th scope="col">Team</th><th scope="col">Telecaller</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr>
                </thead>
                <tbody>
                  {data.items.map((r) => <TelecallerRuleRow key={r.id} rule={r} reports={reports ?? []} onChanged={(text) => { setNotice(text); reload(); }} />)}
                </tbody>
              </table>
            </div>
            {data.total > CATALOGUE_PAGE_SIZE && (
              <nav aria-label="Rule pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(filter, Math.max(0, offset - CATALOGUE_PAGE_SIZE))}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(filter, offset + CATALOGUE_PAGE_SIZE)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
