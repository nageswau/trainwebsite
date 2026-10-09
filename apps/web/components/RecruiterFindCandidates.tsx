"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { PickOption } from "@/lib/lookups";
import { requirementCandidatesUrl } from "@/lib/recruiterApplications";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import {
  availabilityOf, BAND_LABEL, BANDS, type CandidateCard, distinctTerms, EMPTY_SEARCH, EXPERIENCE_LABEL, experienceBand, GROUP_TERMS, isSearchResult,
  MAX_GROUPS, MAX_TERMS, OTHER_LOCATION, PAGE_SIZE, paramsOf, requirementSearch, salaryText, SEARCH_URL, searchBody, type SearchResult,
  type SearchState, stateOf, unknownSkill,
} from "@/lib/recruiterCandidateSearch";
import { CANDIDATES_PATH, experienceLabel, STATUS_LABEL, STATUSES } from "@/lib/recruiterCandidates";
import { STATUS_LABEL as SKILL_STATUS_LABEL } from "@/lib/recruiterCandidateSkills";

type Failure = { message: string; term?: string; suggestions?: string[] } | null;
type Shortlisted = Record<string, { busy?: boolean; text: string; failed?: boolean }>;
const termCount = (s: SearchState) => s.all.length + s.any.reduce((n, g) => n + g.length, 0);

/** One list of skill chips: type a skill and press Enter (or Add); × removes it. The text box's draft is the parent's, so Search can add
 *  a skill typed but not yet added. */
function SkillChips({ id, label, hint, terms, text, room, onText, onChange }: {
  id: string; label: string; hint: string; terms: string[]; text: string; room: boolean; onText: (v: string) => void; onChange: (t: string[]) => void;
}) {
  const add = () => {
    if (!text.trim() || !room) return;
    onChange(distinctTerms([...terms, text], GROUP_TERMS * MAX_GROUPS));
    onText("");
  };
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    add();
  };
  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor={id}>{label}</label>
      <span id={`${id}-hint`} className="muted" style={{ fontSize: 13 }}>{hint}</span>
      {terms.length > 0 && (
        <ul aria-label={label} style={{ listStyle: "none", padding: 0, margin: "6px 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
          {terms.map((term) => (
            <li key={term} className="badge" style={{ alignItems: "center", gap: 4 }}>
              {term}
              <button type="button" aria-label={`Remove ${term}`} onClick={() => onChange(terms.filter((t) => t !== term))}
                style={{ border: 0, background: "transparent", color: "inherit", padding: "0 2px", fontWeight: 800 }}>×</button>
            </li>
          ))}
        </ul>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <input id={id} aria-describedby={`${id}-hint`} value={text} maxLength={120} disabled={!room} onKeyDown={onKey} onChange={(e) => onText(e.target.value)}
          style={{ flex: 1, minWidth: 0 }} />
        <button type="button" className="btn secondary small" onClick={add} disabled={!room || !text.trim()}>Add</button>
      </div>
    </div>
  );
}

function Card({ c, writes, requirement, shortlisted, onShortlist }: {
  c: CandidateCard; writes: boolean; requirement: PickOption | null; shortlisted?: Shortlisted[string]; onShortlist: (c: CandidateCard) => void;
}) {
  const role = [c.preferred_role, experienceLabel(c.experience_months) === "—" ? null : experienceLabel(c.experience_months)].filter(Boolean).join(" | ");
  const facts: [string, string][] = [
    ["Location", c.location ?? "—"], ["Availability", availabilityOf(c.notice_days)], ["Expected salary", salaryText(c.expected_salary)],
    ["Source", c.source_detail ? `${c.source.name} — ${c.source_detail}` : c.source.name], ["Status", STATUS_LABEL[c.status] ?? c.status],
  ];
  return (
    <li className="action-card" style={{ gap: 10 }} aria-labelledby={`card-${c.id}`}>
      <div>
        <h3 id={`card-${c.id}`} style={{ margin: 0, fontSize: 18 }}>
          <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(c.id)}`} style={LINK_STYLE}>{c.name}</Link>{" "}
          <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>{c.candidate_code}</span>
        </h3>
        {role && <p style={{ margin: "2px 0 0", fontWeight: 600 }}>{role}</p>}
        {c.current_company && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Currently at {c.current_company}</p>}
      </div>
      <div>
        <span className="muted" style={{ fontSize: 13 }}>Skills</span>
        {c.skills.length === 0 ? <p className="muted" style={{ margin: 0 }}>No skills recorded</p> : (
          <ul style={{ listStyle: "none", padding: 0, margin: "4px 0 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
            {c.skills.map((s) => (
              <li key={s.name} className={s.matched ? "badge" : undefined}
                style={s.matched ? undefined : { border: "1px solid var(--line)", borderRadius: 99, padding: "4px 10px", fontSize: 12 }}>
                {s.name}{s.status !== "claimed" && <> · {SKILL_STATUS_LABEL[s.status]}</>}
                {s.matched && <span className="visually-hidden"> (matches your search)</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))", gap: "6px 12px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="actions" style={{ gap: 8 }}>
        <Link className="btn secondary small" href={`${CANDIDATES_PATH}/${encodeURIComponent(c.id)}`} aria-label={`View profile of ${c.name}`}>View profile</Link>
        {writes && <Link className="btn secondary small" href={`${CANDIDATES_PATH}/${encodeURIComponent(c.id)}#contact`} aria-label={`Contact ${c.name}`}>Contact</Link>}
        {writes && (
          <button type="button" className="btn small" disabled={!requirement || shortlisted?.busy || (!!shortlisted && !shortlisted.failed)}
            aria-label={`Shortlist ${c.name}`} onClick={() => onShortlist(c)}>
            {shortlisted?.busy ? "Shortlisting…" : shortlisted && !shortlisted.failed ? "Shortlisted" : "Shortlist"}
          </button>
        )}
      </div>
      {shortlisted && !shortlisted.busy && (
        <p className={shortlisted.failed ? "form-error" : "form-message"} role={shortlisted.failed ? "alert" : "status"} style={{ margin: 0 }}>{shortlisted.text}</p>
      )}
    </li>
  );
}

/** rec-013 (spec §5; DEC-SCOPE-141): Find Candidates. The whole search lives in the URL, so refresh keeps it and Back returns to the
 *  previous one (the tel-008 idiom); the form edits a draft that Search (or a facet) pushes. Shortlist and Contact are for writers;
 *  `sourceFilter` is false for hr_team, whom the recruiter catalogue refuses (rec-002 C3). */
export default function RecruiterFindCandidates({ writes, sourceFilter }: { writes: boolean; sourceFilter: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const key = params.toString();
  const [draft, setDraft] = useState<SearchState>(() => stateOf(params));
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<Failure>(null);
  const [version, setVersion] = useState(0);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  const [requirement, setRequirement] = useState<PickOption | null>(null);
  const [shortlisted, setShortlisted] = useState<Shortlisted>({});
  const state = stateOf(new URLSearchParams(key));

  useEffect(() => {
    setDraft(stateOf(new URLSearchParams(key)));
    setTexts({});
  }, [key]);

  useEffect(() => {
    const body = searchBody(stateOf(new URLSearchParams(key)));
    setFailure(null);
    if (!body) {
      setResult(null);
      return;
    }
    const controller = new AbortController();
    const offset = stateOf(new URLSearchParams(key)).offset;
    setLoading(true);
    fetch(`${SEARCH_URL}?limit=${PAGE_SIZE}&offset=${offset}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json().catch(() => null);
        if (response.ok && isSearchResult(data)) return setResult(data);
        setResult(null);
        const unknown = unknownSkill(data?.detail);
        const message = unknown ? String((data.detail as { message?: unknown }).message ?? "") : detailMessage(data?.detail, "Unable to search candidates.");
        setFailure({ message: response.status >= 500 || !message ? "Unable to search candidates." : message, ...(unknown ?? {}) });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setResult(null);
        setFailure({ message: "Unable to search candidates. Check your connection and try again." });
      })
      .finally(() => controller.signal.aborted || setLoading(false));
    return () => controller.abort();
  }, [key, version]);

  useEffect(() => {
    if (!sourceFilter) return;
    const controller = new AbortController(); // a picker that fails to load leaves just "All sources"
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => undefined);
    return () => controller.abort();
  }, [sourceFilter]);

  function go(next: SearchState) {
    const query = paramsOf(next).toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  /** Search adds any skill typed but not yet added, and starts again from the first result. */
  function submit(event: FormEvent) {
    event.preventDefault();
    const all = distinctTerms([...draft.all, texts.all ?? ""], MAX_TERMS);
    const any = draft.any.map((group, i) => distinctTerms([...group, texts[`any${i}`] ?? ""], GROUP_TERMS)).filter((g) => g.length);
    go({ ...draft, all, any, offset: 0 });
  }

  function replaceTerm(term: string, by: string) {
    const swap = (list: string[]) => distinctTerms(list.map((t) => (t.toLowerCase() === term.toLowerCase() ? by : t)));
    go({ ...state, all: swap(state.all), any: state.any.map(swap), offset: 0 });
  }

  async function shortlist(c: CandidateCard) {
    if (!requirement) return;
    setShortlisted((s) => ({ ...s, [c.id]: { busy: true, text: "" } }));
    const outcome = await sendJson(requirementCandidatesUrl(requirement.id), "POST", { candidate_id: c.id, status: "shortlisted" });
    setShortlisted((s) => ({
      ...s, [c.id]: outcome.ok ? { text: `Shortlisted for ${requirement.label}.` } : { text: outcome.message, failed: true },
    }));
  }

  const set = <K extends keyof SearchState>(field: K, value: SearchState[K]) => setDraft((d) => ({ ...d, [field]: value }));
  const room = termCount(draft) < MAX_TERMS;
  const narrow = (changes: Partial<SearchState>) => go({ ...state, ...changes, offset: 0 });
  const searched = searchBody(state) !== null;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <form role="search" aria-label="Find candidates" onSubmit={submit} className="action-card" style={{ gap: 14 }}>
        <SkillChips id="find-all" label="Must have all of these skills" hint="Type a skill or another name for it, then press Enter. Related skills count too."
          terms={draft.all} text={texts.all ?? ""} room={room} onText={(v) => setTexts((t) => ({ ...t, all: v }))} onChange={(all) => set("all", all)} />
        {draft.any.map((group, i) => (
          <div key={i} style={{ borderLeft: "3px solid var(--line)", paddingLeft: 10, display: "grid", gap: 6 }}>
            <SkillChips id={`find-any${i}`} label={`And at least one of these (group ${i + 1})`} hint="A candidate needs any one of these skills."
              terms={group} text={texts[`any${i}`] ?? ""} room={room && group.length < GROUP_TERMS}
              onText={(v) => setTexts((t) => ({ ...t, [`any${i}`]: v }))}
              onChange={(terms) => set("any", draft.any.map((g, n) => (n === i ? terms : g)))} />
            <button type="button" className="btn ghost small" style={{ justifySelf: "start" }}
              onClick={() => { set("any", draft.any.filter((_, n) => n !== i)); setTexts({}); }}>Remove group {i + 1}</button>
          </div>
        ))}
        {draft.any.length < MAX_GROUPS && (
          <button type="button" className="btn ghost small" style={{ justifySelf: "start" }} onClick={() => set("any", [...draft.any, []])}>
            + Add an “at least one of” group
          </button>
        )}
        {!room && <p className="muted" role="status" style={{ margin: 0 }}>You can search for up to {MAX_TERMS} skills at once.</p>}
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={draft.verified} onChange={(e) => set("verified", e.target.checked)} /> Verified skills only
        </label>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: 12 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-exp-min">Experience from (years)</label>
            <input id="find-exp-min" type="number" inputMode="numeric" min={0} max={50} value={draft.expMin} onChange={(e) => set("expMin", e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-exp-max">Experience to (years)</label>
            <input id="find-exp-max" type="number" inputMode="numeric" min={0} max={50} value={draft.expMax} onChange={(e) => set("expMax", e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-location">Location</label>
            <input id="find-location" maxLength={120} value={draft.location} onChange={(e) => set("location", e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-qualification">Qualification</label>
            <input id="find-qualification" maxLength={120} placeholder="e.g. B.Tech" value={draft.qualification} onChange={(e) => set("qualification", e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-sal-min">Expected salary from (₹ lakhs a year)</label>
            <input id="find-sal-min" type="number" inputMode="decimal" min={0} step={0.5} value={draft.salMin} onChange={(e) => set("salMin", e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-sal-max">Expected salary to (₹ lakhs a year)</label>
            <input id="find-sal-max" type="number" inputMode="decimal" min={0} step={0.5} value={draft.salMax} onChange={(e) => set("salMax", e.target.value)} />
          </div>
          {sourceFilter && (
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="find-source">Candidate source</label>
              <select id="find-source" value={draft.sourceId} onChange={(e) => set("sourceId", e.target.value)}>
                <option value="">All sources</option>
                {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          )}
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="find-status">Status</label>
            <select id="find-status" value={draft.status} onChange={(e) => set("status", e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600, marginBottom: 4 }}>Availability (notice period)</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {BANDS.map((b) => (
              <label key={b.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={draft.availability.includes(b.key)}
                  onChange={(e) => set("availability", BANDS.map((x) => x.key).filter((k) => (k === b.key ? e.target.checked : draft.availability.includes(k))))} />
                {b.label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="actions" style={{ gap: 8 }}>
          <button type="submit" className="btn">Search candidates</button>
          <button type="button" className="btn secondary" onClick={() => go(EMPTY_SEARCH)}>Clear all</button>
        </div>
      </form>

      {!searched ? (
        <p className="muted" role="status">Add at least one skill to search every candidate in the pool.</p>
      ) : failure ? (
        <div className="action-card" style={{ gap: 8 }}>
          <p className="form-error" role="alert" style={{ margin: 0 }}>{failure.message}</p>
          {failure.term && failure.suggestions && failure.suggestions.length > 0 && (
            <div className="actions" style={{ gap: 8 }}>
              {failure.suggestions.map((s) => (
                <button key={s} type="button" className="btn secondary small" onClick={() => replaceTerm(failure.term!, s)}>Use {s}</button>
              ))}
            </div>
          )}
          {!failure.term && <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setVersion((v) => v + 1)}>Retry</button>}
        </div>
      ) : result === null ? (
        <p className="muted" role="status">Searching candidates…</p>
      ) : (
        <Results result={result} state={state} loading={loading} writes={writes} requirement={requirement} shortlisted={shortlisted}
          onRequirement={(r) => { setRequirement(r); setShortlisted({}); }} onShortlist={shortlist} narrow={narrow} page={(offset) => go({ ...state, offset })} />
      )}
    </div>
  );
}

function Results({ result, state, loading, writes, requirement, shortlisted, onRequirement, onShortlist, narrow, page }: {
  result: SearchResult; state: SearchState; loading: boolean; writes: boolean; requirement: PickOption | null; shortlisted: Shortlisted;
  onRequirement: (r: PickOption | null) => void; onShortlist: (c: CandidateCard) => void; narrow: (c: Partial<SearchState>) => void; page: (offset: number) => void;
}) {
  const expanded = result.terms.filter((t) => t.also.length || t.skill.name.toLowerCase() !== t.term.toLowerCase());
  const facetButton = (label: string, count: number, onClick?: () => void, pressed = false) => (
    <li key={label}>
      {onClick && count > 0 ? (
        <button type="button" className="btn ghost small" aria-pressed={pressed} onClick={onClick} style={{ width: "100%", justifyContent: "space-between" }}>
          <span>{label}</span><span>{count}</span>
        </button>
      ) : (
        <span style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", fontSize: 13 }} className="muted"><span>{label}</span><span>{count}</span></span>
      )}
    </li>
  );
  const facet = (title: string, items: React.ReactNode[]) => (
    <div>
      <h3 style={{ fontSize: 15, margin: "0 0 4px" }}>{title}</h3>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4 }}>{items}</ul>
    </div>
  );
  return (
    <section aria-label="Search results" aria-busy={loading} style={{ display: "grid", gap: 12 }}>
      <div>
        <div role="status"><h2 style={{ fontSize: 22, margin: 0 }}>{result.total === 1 ? "1 candidate found" : `${result.total} candidates found`}</h2></div>
        {expanded.length > 0 && (
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
            {expanded.map((t) => `${t.term} → ${[t.skill.name, ...t.also].join(", ")}`).join("; ")}
          </p>
        )}
      </div>
      {writes && (
        <div className="action-card" style={{ gap: 6 }}>
          <SearchableSelect label="Shortlist into requirement" noun="requirement" search={requirementSearch} onChange={onRequirement} />
          <span className="muted" style={{ fontSize: 13 }}>
            {requirement ? `Shortlist adds a candidate to ${requirement.label} as Shortlisted.` : "Choose one of your open requirements to shortlist candidates into it."}
          </span>
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
        <aside aria-label="Refine results" className="action-card" style={{ gap: 14, flex: "1 1 14rem", minWidth: 0 }}>
          {facet("Experience", result.facets.experience.map((f) => {
            const band = experienceBand(f.key);
            return facetButton(EXPERIENCE_LABEL[f.key] ?? f.key, f.count, band ? () => narrow(band) : undefined,
              !!band && state.expMin === band.expMin && state.expMax === band.expMax);
          }))}
          {facet("Location", result.facets.location.map((f) => facetButton(
            f.value === null ? "Not recorded" : f.value === OTHER_LOCATION ? "Other" : f.value, f.count,
            f.value && f.value !== OTHER_LOCATION ? () => narrow({ location: f.value! }) : undefined, state.location === f.value,
          )))}
          {facet("Availability", result.facets.availability.map((f) => facetButton(
            BAND_LABEL[f.key] ?? f.key, f.count, f.key === "none" ? undefined : () => narrow({ availability: [f.key as SearchState["availability"][number]] }),
            state.availability.length === 1 && state.availability[0] === f.key,
          )))}
        </aside>
        <div style={{ flex: "3 1 22rem", minWidth: 0, display: "grid", gap: 12 }}>
          {result.items.length === 0 ? (
            <p className="muted" role="status">No candidates match. Remove a skill or a filter to see more.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
              {result.items.map((c) => (
                <Card key={c.id} c={c} writes={writes} requirement={requirement} shortlisted={shortlisted[c.id]} onShortlist={onShortlist} />
              ))}
            </ul>
          )}
          {result.total > PAGE_SIZE && (
            <nav aria-label="Result pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {result.offset + 1}–{result.offset + result.items.length} of {result.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={result.offset === 0} onClick={() => page(Math.max(0, result.offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={result.offset + result.items.length >= result.total} onClick={() => page(result.offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </div>
      </div>
    </section>
  );
}
