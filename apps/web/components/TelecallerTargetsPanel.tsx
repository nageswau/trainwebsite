"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import type { PickOption } from "@/lib/lookups";
import { getPage } from "@/lib/telecallerCatalogue";
import {
  EFFECTIVE_URL, HISTORY_PAGE_SIZE, KPIS, KPI_LABEL, PERIOD_LABEL, TARGETS_URL, TARGET_MAX, earliestDaily, istToday, monthOptions, sourceLabel, targetText,
  telecallerSearch, type TargetPeriod, type TargetRow, type TargetsInEffect, type TargetValue,
} from "@/lib/telecallerTargets";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

type SubjectKind = "it" | "overseas" | "user";
const FEEDBACK_ID = "tgt-feedback";
const SUBJECT_LABEL: Record<SubjectKind, string> = { it: "IT team default", overseas: "Overseas team default", user: "A telecaller (override)" };
const dateText = (iso: string) => formatDate(iso, false, "UTC");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** QA-05: `?for=` is a team, "user" (a telecaller not yet chosen) or a telecaller's id; anything else is the IT team. */
function fromUrl(raw: string | null): { kind: SubjectKind; userId: string | null } {
  if (raw === "it" || raw === "overseas" || raw === "user") return { kind: raw, userId: null };
  return raw && UUID.test(raw) ? { kind: "user", userId: raw } : { kind: "it", userId: null };
}

// tel-022 (DEC-SCOPE-080): the manager's Targets page. Choose a team default or one of your telecallers, see what is in effect today
// and this month, set new values from a future date (G2), and read the history (T28). The API decides every rule.
export default function TelecallerTargetsPanel() {
  // The subject is read from the URL once and replaced on every change, so a refresh keeps it (QA-05).
  const router = useRouter();
  const pathname = usePathname();
  const initial = fromUrl(useSearchParams().get("for"));
  const [kind, setKind] = useState<SubjectKind>(initial.kind);
  const [picked, setPicked] = useState<PickOption | null>(initial.userId ? { id: initial.userId, label: "" } : null);
  const [restoring, setRestoring] = useState(initial.userId !== null); // the picker waits for the restored telecaller's name
  const [period, setPeriod] = useState<TargetPeriod>("daily");
  const today = istToday();
  const [onDate, setOnDate] = useState(today);
  const [from, setFrom] = useState(earliestDaily(today));
  const [values, setValues] = useState<Record<string, string>>({});
  const [useDefault, setUseDefault] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [effective, setEffective] = useState<TargetsInEffect | null>(null);
  const [history, setHistory] = useState<Page<TargetRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const inFlight = useRef(false); // `busy` disables Save only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();

  const isUser = kind === "user";
  const subject = isUser ? (picked ? `user_id=${picked.id}` : null) : `team=${kind}`;
  const historyQuery = isUser ? subject : `scope=team&team=${kind}`;

  useEffect(() => {
    setEffective(null);
    setHistory(null);
    setLoadFailed(false);
    if (!subject) return;
    const controller = new AbortController();
    const effectiveRequest = fetch(`${EFFECTIVE_URL}?${subject}${onDate ? `&date=${onDate}` : ""}`, { signal: controller.signal }).then(async (r) => {
      if (!r.ok) throw new Error(`Request failed (${r.status})`);
      return (await r.json()) as TargetsInEffect;
    });
    const historyRequest = getPage<TargetRow>(`${TARGETS_URL}?${historyQuery}&limit=${HISTORY_PAGE_SIZE}&offset=${offset}`, controller.signal);
    Promise.all([effectiveRequest, historyRequest])
      .then(([e, h]) => {
        setEffective(e);
        setHistory(h);
        if (e.user) setPicked((p) => (p && !p.label ? { id: e.user!.id, label: e.user!.full_name } : p));
        setRestoring(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setLoadFailed(true);
        setRestoring(false);
      });
    return () => controller.abort();
  }, [subject, historyQuery, onDate, offset, version]);

  const remember = (value: string) => router.replace(`${pathname}?for=${value}`, { scroll: false });

  function chooseKind(next: SubjectKind) {
    setKind(next);
    setPicked(null);
    setOffset(0);
    setUseDefault({});
    setFeedback(null);
    remember(next);
  }

  function choosePeriod(next: TargetPeriod) {
    setPeriod(next);
    setFrom(next === "daily" ? earliestDaily(today) : monthOptions(today)[0].value);
  }

  const entered = KPIS.filter((k) => useDefault[k.key] || (values[k.key] ?? "").trim() !== "");

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || entered.length === 0) return;
    if (!from) { // QA-04: a cleared or half-typed date is "" here; the API's parse error would be a Pydantic sentence
      setFeedback({ text: "Choose a start date.", tone: "error" });
      focus(FEEDBACK_ID);
      return;
    }
    const body: Record<string, number | null> = {};
    for (const k of entered) {
      if (useDefault[k.key]) {
        body[k.key] = null;
        continue;
      }
      const text = values[k.key].trim();
      const n = Number(text);
      if (!/^\d+$/.test(text) || n > TARGET_MAX) {
        setFeedback({ text: `${k.label} must be a whole number from 0 to ${TARGET_MAX}.`, tone: "error" });
        focus(FEEDBACK_ID);
        return;
      }
      body[k.key] = n;
    }
    inFlight.current = true;
    setBusy(true);
    const scope = isUser ? { scope: "user", user_id: picked!.id } : { scope: "team", team: kind };
    const outcome = await sendJson(TARGETS_URL, "POST", { ...scope, period, effective_from: from, values: body });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      const count = entered.length;
      setFeedback({ text: `Saved ${count} ${count === 1 ? "target" : "targets"} from ${dateText(from)}.`, tone: "success" });
      setValues({});
      setUseDefault({});
      setOffset(0);
      setVersion((v) => v + 1);
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  const cell = (rows: TargetValue[], kpi: string) => {
    const row = rows.find((r) => r.kpi === kpi);
    const value = row?.value ?? null;
    return (
      <td>
        {targetText(value)}
        {isUser && value !== null && <span className="muted"> ({sourceLabel(row!.source)})</span>}
      </td>
    );
  };
  const monthLabel = effective ? new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${effective.month}T00:00:00Z`)) : "";

  return (
    <>
      <div className="action-card wide tel-targets">
        <h3>Whose targets</h3>
        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor="tgt-subject">Set targets for</label>
          <select id="tgt-subject" value={kind} onChange={(e) => chooseKind(e.target.value as SubjectKind)} disabled={busy}>
            {(Object.keys(SUBJECT_LABEL) as SubjectKind[]).map((k) => <option key={k} value={k}>{SUBJECT_LABEL[k]}</option>)}
          </select>
        </div>
        {isUser && (
          <div style={{ maxWidth: 420 }}>
            {restoring ? <p className="muted" role="status">Loading telecaller…</p> : (
              <SearchableSelect id="tgt-user" label="Telecaller (required)" noun="telecaller" required search={telecallerSearch} disabled={busy}
                initial={picked?.label ? picked : null}
                onChange={(option) => { setPicked(option); setOffset(0); setUseDefault({}); setFeedback(null); remember(option ? option.id : "user"); }} />
            )}
          </div>
        )}
        {subject && (
          <div className="field" style={{ maxWidth: 220 }}>
            <label htmlFor="tgt-on">In effect on</label>
            <input id="tgt-on" type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </div>
        )}
        {!subject ? (
          <p className="muted" role="status">Choose a telecaller to see and set their targets.</p>
        ) : loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load targets.</p>
            <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
          </>
        ) : effective === null ? (
          <p className="muted" role="status">Loading targets…</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="Targets in effect" tabIndex={0}>
            <table className="table">
              <caption className="muted" style={{ textAlign: "left", paddingBottom: 6 }}>In effect on {dateText(effective.date)}{isUser ? " — an override replaces the team default" : ""}</caption>
              <thead><tr><th scope="col">KPI</th><th scope="col">{effective.date === today ? "Today" : dateText(effective.date)} (daily)</th><th scope="col">{monthLabel} (monthly)</th></tr></thead>
              <tbody>
                {KPIS.map((k) => <tr key={k.key}><th scope="row">{k.label}</th>{cell(effective.daily, k.key)}{cell(effective.monthly, k.key)}</tr>)}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {subject && (
        <form className="action-card form tel-targets" onSubmit={save} noValidate aria-describedby={FEEDBACK_ID}>
          <h3>Set new targets</h3>
          <fieldset className="field" disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
            <legend>Period</legend>
            {(["daily", "monthly"] as TargetPeriod[]).map((p) => (
              <label key={p} style={{ marginRight: 16 }}>
                <input type="radio" name="period" value={p} checked={period === p} onChange={() => choosePeriod(p)} /> {PERIOD_LABEL[p]}
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor="tgt-from">Starts on</label>
            {period === "daily" ? (
              <input id="tgt-from" type="date" min={earliestDaily(today)} value={from} required onChange={(e) => setFrom(e.target.value)} disabled={busy} />
            ) : (
              <select id="tgt-from" value={from} onChange={(e) => setFrom(e.target.value)} disabled={busy}>
                {monthOptions(today).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            )}
            <p className="muted" style={{ fontSize: 13 }}>Changes never apply to today or this month; past results keep their targets.</p>
          </div>
          {KPIS.map((k) => (
            <div className="field" key={k.key}>
              <label htmlFor={`tgt-${k.key}`}>{k.label} target</label>
              <input id={`tgt-${k.key}`} type="number" inputMode="numeric" min={0} max={TARGET_MAX} step={1} placeholder="Unchanged"
                value={values[k.key] ?? ""} disabled={busy || !!useDefault[k.key]}
                onChange={(e) => setValues((v) => ({ ...v, [k.key]: e.target.value }))} />
              {isUser && (
                <label className="tel-check" style={{ fontSize: 13 }}>
                  <input type="checkbox" aria-label={`Use team default for ${k.label}`} checked={!!useDefault[k.key]} disabled={busy}
                    onChange={(e) => setUseDefault((d) => ({ ...d, [k.key]: e.target.checked }))} /> Use team default
                </label>
              )}
            </div>
          ))}
          <p className="muted" style={{ fontSize: 13 }}>Leave a KPI blank to keep its current target.</p>
          <button className="btn" disabled={busy || entered.length === 0}>{busy ? "Saving…" : "Save targets"}</button>
          <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
            {feedback?.text}
          </div>
        </form>
      )}

      {subject && history && (
        <div className="action-card wide tel-targets">
          <h3>History</h3>
          {history.items.length === 0 ? (
            <p className="empty" role="status">No targets set yet.</p>
          ) : (
            <>
              <div className="table-wrap" role="region" aria-label="Target history" tabIndex={0}>
                <table className="table">
                  <thead><tr><th scope="col">Starts</th><th scope="col">Period</th><th scope="col">KPI</th><th scope="col">Target</th><th scope="col">Set by</th></tr></thead>
                  <tbody>
                    {history.items.map((r) => (
                      <tr key={r.id}>
                        <td>{dateText(r.effective_from)}</td><td>{PERIOD_LABEL[r.period]}</td><td>{KPI_LABEL[r.kpi] ?? r.kpi}</td>
                        <td>{r.value === null ? "Team default" : r.value}</td><td>{r.set_by.full_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {history.total > HISTORY_PAGE_SIZE && (
                <nav aria-label="History pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                  <span className="muted" style={{ fontSize: 13 }}>Showing {history.offset + 1}–{history.offset + history.items.length} of {history.total}</span>
                  <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - HISTORY_PAGE_SIZE))}>Previous</button>
                  <button type="button" className="btn secondary small" aria-label="Next page" disabled={history.offset + history.items.length >= history.total} onClick={() => setOffset(offset + HISTORY_PAGE_SIZE)}>Next</button>
                </nav>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
