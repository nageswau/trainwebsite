"use client";
import { type FormEvent, useEffect, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import {
  isVacanciesBody, OUTCOME_LABELS, RESPONSE_LABEL, RESPONSES, sharesUrl, type Vacancies, vacanciesUrl, type VacancyOption, vacancyOptionsUrl,
  type VacancyShare,
} from "@/lib/campusPlacement";
import { CHANNEL_LABEL, CHANNELS, dayText } from "@/lib/recruiterColleges";

const SERVER_FAILED = "Something went wrong on our side. Please try again.";
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" } as const;
type Template = { id: string; name: string };

const optional = (form: FormData, key: string) => String(form.get(key) ?? "").trim() || null;

// pob-015 (DEC-SCOPE-426): the vacancies shared with this college (its timeline, newest first), the share form for the college's writers,
// each share's reply, and the outcomes of the college's students. `can_share` decides the forms; the server enforces every rule.
export default function CollegeVacancies({ orgId, onNotice }: { orgId: string; onNotice?: (text: string) => void }) {
  const [data, setData] = useState<Vacancies | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ form: string; message: string } | null>(null);
  const [options, setOptions] = useState<VacancyOption[] | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState({ q: "", run: 0 }); // `run`: the same text searched again still refetches (QA-01)
  const [templates, setTemplates] = useState<Template[]>([]);
  const [answering, setAnswering] = useState<string | null>(null);
  const id = (part: string) => `vacancies-${orgId}-${part}`;
  const canShare = data?.can_share ?? false;

  useEffect(() => {
    let live = true;
    setFailed(false);
    fetch(vacanciesUrl(orgId))
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !isVacanciesBody(body)) throw new Error("not vacancies");
        if (live) setData(body.vacancies);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [orgId, version]);

  useEffect(() => {
    if (!canShare) return;
    let live = true;
    setOptions(null);
    fetch(vacancyOptionsUrl(orgId, search.q))
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { items?: VacancyOption[]; templates?: Template[] } | null) => {
        if (!live) return;
        setOptions(Array.isArray(body?.items) ? body.items : []);
        setTemplates(Array.isArray(body?.templates) ? body.templates : []); // QA-02: the template is optional -- none, no picker
      })
      .catch(() => live && setOptions([]));
    return () => {
      live = false;
    };
  }, [orgId, canShare, search]);

  async function write(form: string, url: string, method: "POST" | "PATCH", body: unknown, done: string): Promise<boolean> {
    setBusy(form);
    setFailure(null);
    setNotice(null);
    const outcome = await sendRequest(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    setBusy(null);
    if (outcome.ok && isVacanciesBody(outcome.data)) {
      setData(outcome.data.vacancies);
      if (onNotice) onNotice(done);
      else setNotice(done);
      return true;
    }
    setFailure({ form, message: !outcome.ok ? ((outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message) : "Unable to save. Please try again." });
    return false;
  }

  async function share(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const d = new FormData(element);
    const body = { requirement_id: optional(d, "requirement_id"), channel: String(d.get("channel")), shared_on: optional(d, "shared_on"),
                   template_id: optional(d, "template_id"), notes: optional(d, "notes") };
    if (!body.requirement_id) {
      setFailure({ form: "share", message: "Choose a vacancy to share." });
      return;
    }
    if (await write("share", sharesUrl(orgId), "POST", body, "Vacancy share recorded.")) element.reset();
  }

  const runSearch = () => setSearch((s) => ({ q: query, run: s.run + 1 }));
  const errorFor = (form: string) => failure?.form === form && <p className="form-error" role="alert">{failure.message}</p>;
  const titleId = id("title");

  if (failed) {
    return (
      <section className="action-card wide" aria-labelledby={titleId}>
        <h3 id={titleId}>Vacancies shared</h3>
        <p className="form-error">Unable to load the vacancies shared with this college.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="action-card wide" aria-labelledby={titleId} aria-busy="true">
        <h3 id={titleId}>Vacancies shared</h3>
        <p className="muted">Loading the vacancies shared…</p>
      </section>
    );
  }

  const answer = (s: VacancyShare) => (
    <form className="form" noValidate style={ROW} aria-label={`Reply to ${s.requirement.title}`}
      onSubmit={async (event) => {
        event.preventDefault();
        const d = new FormData(event.currentTarget);
        const saved = await write(`answer-${s.id}`, sharesUrl(orgId, s.id), "PATCH", { response: String(d.get("response")), response_note: optional(d, "response_note") }, "Reply saved.");
        if (saved) setAnswering(null);
      }}>
      <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
        <label htmlFor={id(`response-${s.id}`)}>Reply</label>
        <select id={id(`response-${s.id}`)} name="response" defaultValue={s.response}>
          {RESPONSES.map((r) => <option key={r} value={r}>{RESPONSE_LABEL[r]}</option>)}
        </select>
      </div>
      <div className="field" style={{ flex: "2 1 220px", margin: 0 }}>
        <label htmlFor={id(`note-${s.id}`)}>Note (optional)</label>
        <input id={id(`note-${s.id}`)} name="response_note" maxLength={500} defaultValue={s.response_note ?? ""} />
      </div>
      <button type="submit" className="btn small" disabled={busy !== null}>{busy === `answer-${s.id}` ? "Saving…" : "Save reply"}</button>
      <button type="button" className="btn secondary small" onClick={() => setAnswering(null)}>Cancel</button>
      {errorFor(`answer-${s.id}`)}
    </form>
  );

  const o = data.outcomes;
  return (
    <section className="action-card wide telecaller-list" aria-labelledby={titleId}>
      <h3 id={titleId}>Vacancies shared</h3>
      {!onNotice && <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>}

      <h4>Student outcomes</h4>
      <ul aria-label="Student outcomes" style={{ display: "flex", flexWrap: "wrap", gap: 16, listStyle: "none", padding: 0, margin: "0 0 8px" }}>
        {OUTCOME_LABELS.map(([key, label]) => (
          <li key={key}><strong style={{ fontSize: 20, display: "block" }}>{o[key]}</strong><span className="muted">{label}</span></li>
        ))}
      </ul>
      <p className="muted" style={{ marginTop: 0 }}>
        {o.students} student{o.students === 1 ? "" : "s"} from this college, {o.external} application{o.external === 1 ? "" : "s"} by external candidates
        (imported by the college or added through a drive here). Students you are not permitted to see are not counted.
      </p>

      {canShare && (
        <>
          <h4>Share a vacancy</h4>
          <div style={{ ...ROW, marginBottom: 8 }}>
            <div className="field" style={{ flex: "2 1 220px", margin: 0 }}>
              <label htmlFor={id("search")}>Find a vacancy</label>
              <input id={id("search")} type="search" value={query} maxLength={120} onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); runSearch(); } }} />
            </div>
            <button type="button" className="btn secondary small" onClick={runSearch}>Search vacancies</button>
          </div>
          <form className="form" noValidate aria-label="Share a vacancy" onSubmit={share}>
            <div style={ROW}>
              <div className="field" style={{ flex: "2 1 260px", margin: 0 }}>
                <label htmlFor={id("requirement")}>Vacancy</label>
                <select id={id("requirement")} name="requirement_id" defaultValue="" required disabled={options === null} key={options?.map((x) => x.id).join() ?? "loading"}>
                  <option value="">{options === null ? "Loading vacancies…" : options.length ? "Choose a vacancy" : "No open vacancies match"}</option>
                  {options?.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.title} · {x.company_name}</option>)}
                </select>
              </div>
              <div className="field" style={{ flex: "1 1 140px", margin: 0 }}>
                <label htmlFor={id("channel")}>Shared by</label>
                <select id={id("channel")} name="channel" defaultValue="email">
                  {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
                </select>
              </div>
              <div className="field" style={{ flex: "0 1 170px", margin: 0 }}>
                <label htmlFor={id("on")}>Shared on (blank = today)</label>
                <input id={id("on")} name="shared_on" type="date" />
              </div>
              {templates.length > 0 && (
                <div className="field" style={{ flex: "1 1 200px", margin: 0 }}>
                  <label htmlFor={id("template")}>Template (optional)</label>
                  <select id={id("template")} name="template_id" defaultValue="">
                    <option value="">None</option>
                    {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
              )}
            </div>
            <div className="field">
              <label htmlFor={id("notes")}>Notes (optional)</label>
              <input id={id("notes")} name="notes" maxLength={500} />
            </div>
            <button type="submit" className="btn small" disabled={busy !== null}>{busy === "share" ? "Recording…" : "Record share"}</button>
            {errorFor("share")}
          </form>
        </>
      )}

      <h4>Shared with this college</h4>
      {data.shares.length === 0 ? <p className="empty">No vacancies shared with this college yet.</p> : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {data.shares.map((s) => (
            <li key={s.id} style={{ borderTop: "1px solid var(--line, #e5e7eb)", padding: "8px 0" }}>
              <div style={{ overflowWrap: "anywhere" }}>
                <strong>{s.requirement.code} · {s.requirement.title}</strong> · {dayText(s.shared_on)} · {CHANNEL_LABEL[s.channel] ?? s.channel}
                {s.template && <> · Template: {s.template.name}</>}
              </div>
              {s.notes && <div style={{ overflowWrap: "anywhere" }}>{s.notes}</div>}
              <div>
                <span className="badge">{RESPONSE_LABEL[s.response] ?? s.response}</span>
                {s.response_note && <span style={{ marginLeft: 6, overflowWrap: "anywhere" }}>{s.response_note}</span>}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                Shared by {s.shared_by_name}{s.responded_by_name ? ` · Reply recorded by ${s.responded_by_name}` : ""}
              </div>
              {canShare && (answering === s.id ? answer(s) : (
                <button type="button" className="btn secondary small" aria-label={`Record the reply for ${s.requirement.title}`} onClick={() => setAnswering(s.id)}>Record reply</button>
              ))}
            </li>
          ))}
        </ul>
      )}
      {data.share_total > data.shares.length && <p className="muted">Showing the latest {data.shares.length} of {data.share_total} shares.</p>}
    </section>
  );
}
