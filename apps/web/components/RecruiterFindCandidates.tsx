"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import RecruiterBulkTaskForm, { type BulkSkip, type BulkTaskResult } from "@/components/RecruiterBulkTaskForm";
import RecruiterSavedSearches from "@/components/RecruiterSavedSearches";
import RecruiterShareDialog, { type ShareCandidate } from "@/components/RecruiterShareDialog";
import SearchableSelect from "@/components/SearchableSelect";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { PickOption } from "@/lib/lookups";
import { requirementCandidatesUrl } from "@/lib/recruiterApplications";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import {
  activeFilters, availabilityOf, BAND_LABEL, BANDS, type CandidateCard, distinctTerms, EMPTY_SEARCH, EXPERIENCE_LABEL, experienceBand, EXPORT_PERMISSION,
  EXPORT_URL, FILTERS,
  type FilterGroup, type FilterSpec, GROUP_TERMS, isSearchResult, matchSummary, MAX_GROUPS, MAX_TERMS, OTHER_LOCATION, PAGE_SIZE, paramsOf,
  PREFERRED_MAX, requirementSearch, salaryText, SEARCH_URL, searchBody, type SearchResult, type SearchState, searchText, type SortKey, sortOptions,
  stateOf, TEXT_MAX, unknownSkill,
} from "@/lib/recruiterCandidateSearch";
import { CANDIDATES_PATH, COMPENSATION_VIEW, ENGAGEMENTS, experienceLabel, STATUS_LABEL, STATUSES } from "@/lib/recruiterCandidates";
import { STATUS_LABEL as SKILL_STATUS_LABEL } from "@/lib/recruiterCandidateSkills";
import { SKILL_CATEGORIES_URL } from "@/lib/recruiterSkills";
import { usePermissions } from "@/lib/usePermissions";

type Failure = { message: string; retry: boolean; term?: string; suggestions?: string[] } | null;
type Shortlisted = Record<string, { busy?: boolean; text: string; failed?: boolean }>;
type Category = { id: string; name: string; active: boolean };
const termCount = (s: SearchState) => s.all.length + s.any.reduce((n, g) => n + g.length, 0) + s.preferred.length;
const GRID = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: 12 } as const;
const FIELD = { marginBottom: 0 } as const;

/** hrc-019: one collapsible filter group. It opens when the search in the URL uses it (`count`), or by default for the groups that held
 *  the rec-013 filters (they stayed in view before the regrouping). A closed group renders no controls until it is opened. */
function Section({ title, count, open = false, children }: { title: string; count: number; open?: boolean; children: React.ReactNode }) {
  const [shown, setShown] = useState(open || count > 0);
  useEffect(() => {
    if (count > 0) setShown(true);
  }, [count]);
  return (
    <details open={shown} onToggle={(e) => setShown(e.currentTarget.open)} style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "8px 12px" }}>
      <summary style={{ fontWeight: 600, cursor: "pointer" }}>{count > 0 ? `${title} (${count})` : title}</summary>
      {shown && <div style={{ ...GRID, marginTop: 10 }}>{children}</div>}
    </details>
  );
}

/** hrc-019: one FILTERS entry as a form control; its draft values are strings, checked by `stateOf` once they reach the URL. */
function FilterField({ spec, values, categories, tags = [], onChange }: {
  spec: FilterSpec; values: string[]; categories: Category[]; tags?: Category[]; onChange: (values: string[]) => void;
}) {
  const id = `find-${spec.param}`;
  const one = values[0] ?? "";
  const set = (value: string) => onChange(value ? [value] : []);
  const toggle = (key: string, on: boolean) => onChange(on ? [...values, key] : values.filter((v) => v !== key));
  if (spec.kind === "flag") {
    return (
      <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <input id={id} type="checkbox" checked={one === "1"} onChange={(e) => set(e.target.checked ? "1" : "")} /> {spec.label}
      </label>
    );
  }
  if (spec.kind === "multi" || spec.kind === "category" || spec.kind === "tag") {
    const listed = spec.kind === "category" ? categories : tags; // pob-019 T4: the active "Candidate tags"
    const options = spec.kind === "multi" ? spec.options ?? [] : listed.filter((c) => c.active || values.includes(c.id)).map((c) => ({ key: c.id, label: c.name }));
    return (
      <fieldset style={{ border: 0, padding: 0, margin: 0, gridColumn: "1 / -1" }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>{spec.label}</legend>
        {options.length === 0 ? <p className="muted" style={{ margin: 0 }}>None to choose from yet.</p> : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px" }}>
            {options.map((o) => (
              <label key={o.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={values.includes(o.key)} onChange={(e) => toggle(o.key, e.target.checked)} /> {o.label}
              </label>
            ))}
          </div>
        )}
      </fieldset>
    );
  }
  if (spec.kind === "choice" || spec.kind === "yesno") {
    return (
      <div className="field" style={FIELD}>
        <label htmlFor={id}>{spec.label}</label>
        <select id={id} value={one} onChange={(e) => set(e.target.value)}>
          <option value="">Any</option>
          {spec.options?.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
    );
  }
  const input = {
    text: { maxLength: 120 }, date: { type: "date" }, years: { type: "number", inputMode: "numeric", min: 0, max: 50 },
    year: { type: "number", inputMode: "numeric", min: 1950, max: 2100 }, cgpa: { type: "number", inputMode: "decimal", min: 0, max: 10, step: 0.1 },
    lakhs: { type: "number", inputMode: "decimal", min: 0, step: 0.5 },
  }[spec.kind] as React.InputHTMLAttributes<HTMLInputElement>;
  return (
    <div className="field" style={FIELD}>
      <label htmlFor={id}>{spec.label}</label>
      <input id={id} {...input} value={one} onChange={(e) => set(e.target.value)} />
    </div>
  );
}

/** One list of skill chips: type a skill and press Enter (or Add); × removes it. The text box's draft is the parent's, so Search can add
 *  a skill typed but not yet added. */
export function SkillChips({ id, label, hint, terms, text, room, onText, onChange }: {
  id: string; label: string; hint: string; terms: string[]; text: string; room: boolean; onText: (v: string) => void; onChange: (t: string[]) => void;
}) {
  const add = () => {
    if (!text.trim() || !room) return;
    onChange(distinctTerms([...terms, text]));
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
        <ul aria-label={`${label}: chosen`} style={{ listStyle: "none", padding: 0, margin: "6px 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
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

export function Card({ c, writes, requirement, shortlisted, onShortlist, matchNote = "matches your search", selected = null, onSelect }: {
  c: CandidateCard; writes: boolean; requirement: PickOption | null; shortlisted?: Shortlisted[string]; onShortlist: (c: CandidateCard) => void;
  matchNote?: string; // rec-015: a talent pool's page says "matches this pool"
  selected?: boolean | null; onSelect?: (on: boolean) => void; // rec-019 / pob-019: select for a bulk action (null = not offered)
}) {
  const role = [c.preferred_role, experienceLabel(c.experience_months) === "—" ? null : experienceLabel(c.experience_months)].filter(Boolean).join(" | ");
  const facts: [string, React.ReactNode][] = [
    ["Location", c.location ?? "—"], ["Availability", availabilityOf(c.notice_days)],
    // hrc-001 H2: left out without the grant; hrc-011 C6: the yearly rupee figure the salary filter compares
    ...(c.expected_salary === undefined ? [] : [["Expected salary", salaryText(c.expected_annual_inr ?? null)] as [string, string]]),
    ["Source", c.source_detail ? `${c.source.name} — ${c.source_detail}` : c.source.name], ["Status", STATUS_LABEL[c.status] ?? c.status],
    ...(c.engagement ? [["Engagement", c.engagement.label] as [string, string]] : []), // hrc-021
    // pob-019 (T5, AC1): owner, last contact, open applications and submissions -- present on every card the API enriches
    ...(c.active_applications === undefined ? [] : [
      ["Owner", c.owner?.full_name ?? "Unassigned"], ["Last contacted", c.last_contacted_at ? <LocalTime value={c.last_contacted_at} /> : "Never"],
      ["Active applications", String(c.active_applications)], ["Prior submissions", String(c.prior_submissions ?? 0)],
    ] as [string, React.ReactNode][]),
  ];
  const tags = [...(c.tags ?? []).map((t) => ({ key: t.id, label: t.name, free: true })),
    ...(c.system_tags ?? []).map((t) => ({ key: `${t.kind}:${t.label}`, label: t.label, free: false }))];
  const why = matchSummary(c.match); // hrc-019 S11
  return (
    <li className="action-card" style={{ gap: 10 }} aria-labelledby={`card-${c.id}`}>
      <div>
        {selected !== null && ( // QA-03: outside the heading, so the card's name stays the candidate's
          <input type="checkbox" checked={selected} onChange={(e) => onSelect?.(e.target.checked)} aria-label={`Select ${c.name}`} style={{ float: "left", margin: "6px 8px 0 0" }} />
        )}
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
                {s.matched && <span className="visually-hidden"> ({matchNote})</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {tags.length > 0 && ( // pob-019 T3/T5: free tags filled, system tags (experience band, skill categories) outlined
        <ul aria-label="Tags" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {tags.map((t) => (
            <li key={t.key} className={t.free ? "badge" : undefined}
              style={t.free ? undefined : { border: "1px dashed var(--line)", borderRadius: 99, padding: "4px 10px", fontSize: 12 }}>{t.label}</li>
          ))}
        </ul>
      )}
      {why && (
        <div>
          <span className="muted" style={{ fontSize: 13 }}>Why matched</span>
          <p style={{ margin: "2px 0 0", fontSize: 14 }}>
            {[why.matched.length ? `Matches: ${why.matched.join(", ")}` : "", why.missing.length ? `Missing nice-to-have: ${why.missing.join(", ")}` : ""]
              .filter(Boolean).join(" · ")}
          </p>
        </div>
      )}
      {c.snippet && c.snippet.length > 0 && (
        <div>
          <span className="muted" style={{ fontSize: 13 }}>From the resume</span>
          <p style={{ margin: "2px 0 0", fontSize: 14, overflowWrap: "anywhere" }}>
            {c.snippet.map((s, i) => (s.hit ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
          </p>
        </div>
      )}
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

/** rec-013 (spec §5; DEC-SCOPE-151): Find Candidates. The whole search lives in the URL, so refresh keeps it and Back returns to the
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
  const [categories, setCategories] = useState<Category[]>([]); // hrc-019: the skill-category filter's choices and chip names
  const [tags, setTags] = useState<CatalogueValue[]>([]); // pob-019: the tag filter's choices and chip names
  const [bulkBusy, setBulkBusy] = useState(false); // T11: one bulk request at a time
  const [report, setReport] = useState<{ text: string; lines: string[]; failed?: boolean } | null>(null);
  const [assigning, setAssigning] = useState(false);
  const permissions = usePermissions();
  const compensation = !!permissions?.includes(COMPENSATION_VIEW); // hrc-001 H2: no salary filter without the grant
  const exports = !!permissions?.includes(EXPORT_PERMISSION); // hrc-020 X8: the API refuses the rest; the button is hidden
  const [exporting, setExporting] = useState<"csv" | "xlsx" | null>(null);
  const [exportError, setExportError] = useState("");
  const [shortlisted, setShortlisted] = useState<Shortlisted>({});
  const [selected, setSelected] = useState<Map<string, ShareCandidate>>(new Map()); // rec-019: kept across pages until shared
  const [sharing, setSharing] = useState<ShareCandidate[] | null>(null); // the selection when the dialog opened (QA-01)
  const select = (c: CandidateCard, on: boolean) => setSelected((current) => {
    const next = new Map(current);
    if (on) next.set(c.id, { id: c.id, name: c.name, code: c.candidate_code });
    else next.delete(c.id);
    return next;
  });
  const resultsRef = useRef<HTMLDivElement>(null);
  const jump = useRef(false); // QA-03: a Search from the form brings its results into view; a facet or a link does not
  const state = stateOf(new URLSearchParams(key));

  useEffect(() => {
    setDraft(stateOf(new URLSearchParams(key)));
    setTexts({});
  }, [key]);

  useEffect(() => {
    const current = stateOf(new URLSearchParams(key));
    const body = searchBody(current);
    setFailure(null);
    if (!body) {
      setResult(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    fetch(`${SEARCH_URL}?limit=${PAGE_SIZE}&offset=${current.offset}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json().catch(() => null);
        if (response.ok && isSearchResult(data)) return setResult(data);
        setResult(null);
        const unknown = unknownSkill(data?.detail);
        const message = unknown ? String((data.detail as { message?: unknown }).message ?? "") : detailMessage(data?.detail, "Unable to search candidates.");
        const broken = response.status >= 500 || !message;
        setFailure({ message: broken ? "Unable to search candidates." : message, retry: broken, ...(unknown ?? {}) }); // QA-02: a 4xx needs an edit, not a retry
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setResult(null);
        setFailure({ message: "Unable to search candidates. Check your connection and try again.", retry: true });
      })
      .finally(() => controller.signal.aborted || setLoading(false));
    return () => controller.abort();
  }, [key, version]);

  useEffect(() => {
    if (!jump.current || (!result && !failure)) return;
    jump.current = false;
    resultsRef.current?.scrollIntoView({ block: "start" });
    resultsRef.current?.focus({ preventScroll: true });
  }, [result, failure]);

  useEffect(() => {
    if (!sourceFilter) return;
    const controller = new AbortController(); // a picker that fails to load leaves just "All sources"
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => undefined);
    activeValues("candidate-tags", controller.signal).then(setTags).catch(() => undefined); // pob-019: the same readers as the sources
    return () => controller.abort();
  }, [sourceFilter]);

  useEffect(() => {
    if (!sourceFilter) return; // QA-01: hr_team cannot read the Skills Master (the same roles the catalogue refuses), so no category filter
    const controller = new AbortController(); // a list that fails to load leaves the category filter empty, never the page broken
    fetch(`${SKILL_CATEGORIES_URL}?limit=100`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((page: { items?: Category[] } | null) => setCategories(Array.isArray(page?.items) ? page.items.filter((c) => c && c.id && c.name) : []))
      .catch(() => undefined);
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
    const preferred = distinctTerms([...draft.preferred, texts.pref ?? ""], PREFERRED_MAX);
    const next = { ...draft, text: searchText(draft.text), all, any, preferred, offset: 0 };
    if (!searchBody(next)) return go(next);
    jump.current = true;
    if (paramsOf(next).toString() === key && (result || failure)) {
      jump.current = false; // the same search: nothing reloads, so just show it
      resultsRef.current?.scrollIntoView({ block: "start" });
    }
    go(next);
  }

  /** hrc-020 (X8-X11): the applied search (the URL's, not the draft) as a file; the API checks the grant, the cap and the throttle. */
  async function exportAs(format: "csv" | "xlsx") {
    const body = searchBody(state);
    if (!body || exporting) return;
    setExporting(format);
    setExportError("");
    try {
      const response = await fetch(`${EXPORT_URL}?format=${format}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setExportError(detailMessage(data?.detail, "Unable to export these candidates."));
        return;
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `candidates.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setExportError("Unable to export these candidates. Check your connection and try again.");
    } finally {
      setExporting(null);
    }
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

  const nameOf = (candidateId: string) => selected.get(candidateId)?.name ?? "A candidate";
  const skippedLines = (skipped: BulkSkip[]) => skipped.map((s) => `${nameOf(s.candidate_id)}: ${s.message}`);
  const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

  /** pob-019 (T7/T8, AC2): one call for the whole selection; the added leave the selection, the skipped stay with their reason. */
  async function bulkShortlist() {
    if (!requirement || bulkBusy || selected.size === 0) return;
    setBulkBusy(true);
    setReport(null);
    const outcome = await sendJson(`${requirementCandidatesUrl(requirement.id)}/bulk`, "POST", { candidate_ids: [...selected.keys()] });
    setBulkBusy(false);
    if (!outcome.ok) return setReport({ text: outcome.message, lines: [], failed: true });
    const { added, skipped } = outcome.data as unknown as { added: { candidate_id: string }[]; skipped: BulkSkip[] };
    setReport({ text: `Shortlisted ${plural(added.length, "candidate")} for ${requirement.label}.`, lines: skippedLines(skipped) });
    setShortlisted((s) => ({ ...s, ...Object.fromEntries(added.map((a) => [a.candidate_id, { text: `Shortlisted for ${requirement.label}.` }])) }));
    setSelected((current) => {
      const next = new Map(current);
      added.forEach((a) => next.delete(a.candidate_id));
      return next;
    });
  }

  function tasksDone(result: BulkTaskResult) {
    setAssigning(false);
    setReport({ text: `Created ${plural(result.created.length, "task")}.`, lines: skippedLines(result.skipped) });
  }

  const set = <K extends keyof SearchState>(field: K, value: SearchState[K]) => setDraft((d) => ({ ...d, [field]: value }));
  const room = termCount(draft) < MAX_TERMS;
  const narrow = (changes: Partial<SearchState>) => go({ ...state, ...changes, offset: 0 });
  const searched = searchBody(state) !== null;
  // hrc-019: the spec-driven groups, their applied-filter counts and the active-filter chips
  const setMore = (param: string, values: string[]) => setDraft((d) => {
    const more = { ...d.more };
    if (values.length) more[param] = values;
    else delete more[param];
    return { ...d, more };
  });
  // hr_team reads neither the Skills Master nor the recruiter catalogue, so it gets no category or tag filter (QA-01)
  const offered = (spec: FilterSpec) => (!spec.package || compensation) && ((spec.kind !== "category" && spec.kind !== "tag") || sourceFilter);
  const fields = (group: FilterGroup) => FILTERS.filter((spec) => spec.group === group && offered(spec)).map((spec) => (
    <FilterField key={spec.param} spec={spec} values={draft.more[spec.param] ?? []} categories={categories} tags={tags} onChange={(v) => setMore(spec.param, v)} />
  ));
  const applied = (group: FilterGroup, ...own: unknown[]) =>
    FILTERS.filter((spec) => spec.group === group).reduce((n, spec) => n + (state.more[spec.param]?.length ?? 0), 0) + own.filter(Boolean).length;
  const chips = activeFilters(state, {
    categories: Object.fromEntries(categories.map((c) => [c.id, c.name])), sources: Object.fromEntries(sources.map((s) => [s.id, s.name])),
    tags: Object.fromEntries(tags.map((t) => [t.id, t.name])),
  });
  const n = selected.size;
  const bulkBar = writes && n > 0 ? ( // pob-019 T12: the selection's actions (Share and Shortlist need a requirement)
    <div style={{ display: "grid", gap: 8 }}>
      <div className="actions" role="group" aria-label="Selected candidates" style={{ gap: 8, alignItems: "center" }}>
        <span style={{ fontWeight: 600 }}>{n} selected</span>
        <button type="button" className="btn small" disabled={!requirement || bulkBusy} onClick={bulkShortlist}>
          {bulkBusy ? "Shortlisting…" : `Shortlist selected (${n})`}
        </button>
        <button type="button" className="btn secondary small" disabled={!requirement} onClick={() => setSharing([...selected.values()])}>Share selected ({n})</button>
        <button type="button" className="btn secondary small" aria-expanded={assigning} onClick={() => { setAssigning((a) => !a); setReport(null); }}>Assign task ({n})</button>
        <button type="button" className="btn ghost small" onClick={() => { setSelected(new Map()); setAssigning(false); }}>Clear selection</button>
      </div>
      {assigning && <RecruiterBulkTaskForm candidateIds={[...selected.keys()]} requirement={requirement} onDone={tasksDone} onCancel={() => setAssigning(false)} />}
    </div>
  ) : null;
  const bulkReport = report && ( // outside the bar, so it stays once the selection empties
    <div role={report.failed ? "alert" : "status"}>
      <p className={report.failed ? "form-error" : "form-message"} style={{ margin: 0 }}>{report.text}</p>
      {report.lines.length > 0 && <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 14 }}>{report.lines.map((line) => <li key={line}>{line}</li>)}</ul>}
    </div>
  );

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <RecruiterSavedSearches state={state} onLoad={(next) => go({ ...next, offset: 0 })} />
      <form role="search" aria-label="Find candidates" onSubmit={submit} className="action-card" style={{ gap: 14 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="find-text">Resume search</label>
          <span id="find-text-hint" className="muted" style={{ fontSize: 13 }}>
            Words anywhere in the candidate&apos;s latest resume — job titles, certifications, projects. Use &quot;quotes&quot; for a phrase.
          </span>
          <input id="find-text" aria-describedby="find-text-hint" maxLength={TEXT_MAX} placeholder="e.g. Microservices Kafka"
            value={draft.text} onChange={(e) => set("text", e.target.value)} />
        </div>
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
        <SkillChips id="find-pref" label="Nice to have (ranks, never excludes)" hint="Candidates holding these come first with “Most matching skills”."
          terms={draft.preferred} text={texts.pref ?? ""} room={room && draft.preferred.length < PREFERRED_MAX}
          onText={(v) => setTexts((t) => ({ ...t, pref: v }))} onChange={(preferred) => set("preferred", preferred)} />
        {!room && <p className="muted" role="status" style={{ margin: 0 }}>You can search for up to {MAX_TERMS} skills at once.</p>}
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={draft.verified} onChange={(e) => set("verified", e.target.checked)} /> Verified skills only
        </label>
        <Section title="More skill filters" count={applied("skills")}>{fields("skills")}</Section>
        <Section title="Experience" count={applied("experience", state.expMin, state.expMax)} open>
          <div className="field" style={FIELD}>
            <label htmlFor="find-exp-min">Experience from (years)</label>
            <input id="find-exp-min" type="number" inputMode="numeric" min={0} max={50} value={draft.expMin} onChange={(e) => set("expMin", e.target.value)} />
          </div>
          <div className="field" style={FIELD}>
            <label htmlFor="find-exp-max">Experience to (years)</label>
            <input id="find-exp-max" type="number" inputMode="numeric" min={0} max={50} value={draft.expMax} onChange={(e) => set("expMax", e.target.value)} />
          </div>
          {fields("experience")}
        </Section>
        <Section title="Education" count={applied("education", state.qualification)}>
          <div className="field" style={FIELD}>
            <label htmlFor="find-qualification">Qualification</label>
            <input id="find-qualification" maxLength={120} placeholder="e.g. B.Tech" value={draft.qualification} onChange={(e) => set("qualification", e.target.value)} />
          </div>
          {fields("education")}
        </Section>
        <Section title="Location" count={applied("location", state.location)} open>
          <div className="field" style={FIELD}>
            <label htmlFor="find-location">Location</label>
            <input id="find-location" maxLength={120} value={draft.location} onChange={(e) => set("location", e.target.value)} />
          </div>
          {fields("location")}
        </Section>
        <Section title="Preferences" count={applied("preferences")}>{fields("preferences")}</Section>
        {compensation && (
          <Section title="Package" count={applied("package", state.salMin, state.salMax)} open>
            <div className="field" style={FIELD}>
              <label htmlFor="find-sal-min">Expected salary from (₹ lakhs a year)</label>
              <input id="find-sal-min" type="number" inputMode="decimal" min={0} step={0.5} value={draft.salMin} onChange={(e) => set("salMin", e.target.value)} />
            </div>
            <div className="field" style={FIELD}>
              <label htmlFor="find-sal-max">Expected salary to (₹ lakhs a year)</label>
              <input id="find-sal-max" type="number" inputMode="decimal" min={0} step={0.5} value={draft.salMax} onChange={(e) => set("salMax", e.target.value)} />
            </div>
            {fields("package")}
          </Section>
        )}
        <Section title="Status and recruitment" count={applied("recruitment", state.sourceId, state.status, state.engagement)} open>
          {sourceFilter && (
            <div className="field" style={FIELD}>
              <label htmlFor="find-source">Candidate source</label>
              <select id="find-source" value={draft.sourceId} onChange={(e) => set("sourceId", e.target.value)}>
                <option value="">All sources</option>
                {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          )}
          <div className="field" style={FIELD}>
            <label htmlFor="find-status">Status</label>
            <select id="find-status" value={draft.status} onChange={(e) => set("status", e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
          <div className="field" style={FIELD}>
            <label htmlFor="find-engagement">Engagement</label>
            <select id="find-engagement" value={draft.engagement} onChange={(e) => set("engagement", e.target.value)}>
              <option value="">All engagement</option>
              {ENGAGEMENTS.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
            </select>
          </div>
          {fields("recruitment")}
        </Section>
        <Section title="Documents and applications" count={applied("records")}>{fields("records")}</Section>
        <Section title="Availability (notice period)" count={state.availability.length} open>
          <fieldset style={{ border: 0, padding: 0, margin: 0, gridColumn: "1 / -1" }}>
            <legend className="visually-hidden">Availability (notice period)</legend>
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
        </Section>
        <div className="actions" style={{ gap: 8 }}>
          <button type="submit" className="btn">Search candidates</button>
          <button type="button" className="btn secondary" onClick={() => go(EMPTY_SEARCH)}>Clear all</button>
        </div>
      </form>

      <div ref={resultsRef} tabIndex={-1} style={{ outline: "none", scrollMarginTop: 80, display: "grid", gap: 12 }}>
      {searched && chips.length > 0 && ( // hrc-019 AC2: each filter can be cleared on its own
        <ul aria-label="Active filters" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {chips.map((chip) => (
            <li key={chip.key} className="badge" style={{ alignItems: "center", gap: 4 }}>
              {chip.label}
              <button type="button" aria-label={`Remove ${chip.label}`} onClick={() => go(chip.clear(state))}
                style={{ border: 0, background: "transparent", color: "inherit", padding: "0 2px", fontWeight: 800 }}>×</button>
            </li>
          ))}
        </ul>
      )}
      {!searched ? (
        <p className="muted" role="status">Add a skill or a resume search to search every candidate in the pool.</p>
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
          {failure.retry && <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => setVersion((v) => v + 1)}>Retry</button>}
        </div>
      ) : result === null ? (
        <p className="muted" role="status">Searching candidates…</p>
      ) : (
        <>
          {sharing && requirement && (
            <RecruiterShareDialog requirement={requirement} candidates={sharing} onClose={() => setSharing(null)} onShared={() => setSelected(new Map())} />
          )}
          <Results result={result} state={state} loading={loading} writes={writes} requirement={requirement} shortlisted={shortlisted}
            onRequirement={(r) => { setRequirement(r); setShortlisted({}); setSharing(null); setReport(null); }} onShortlist={shortlist} narrow={narrow}
            page={(offset) => go({ ...state, offset })} selected={selected} onSelect={select} bulkBar={<>{bulkBar}{bulkReport}</>}
            sorts={sortOptions(compensation)} onSort={(sort) => narrow({ sort })}
            exportBar={exports && result.total > 0 ? (
              <div className="actions" style={{ gap: 6, alignItems: "center" }}>
                <button type="button" className="btn secondary small" disabled={!!exporting} onClick={() => exportAs("csv")}>
                  {exporting === "csv" ? "Exporting…" : "Export CSV"}
                </button>
                <button type="button" className="btn secondary small" disabled={!!exporting} onClick={() => exportAs("xlsx")}>
                  {exporting === "xlsx" ? "Exporting…" : "Export Excel"}
                </button>
                {exportError && <span className="form-error" role="alert">{exportError}</span>}
              </div>
            ) : null} />
        </>
      )}
      </div>
    </div>
  );
}

function Results({ result, state, loading, writes, requirement, shortlisted, onRequirement, onShortlist, narrow, page, selected, onSelect, bulkBar, sorts, onSort,
  exportBar = null }: {
  result: SearchResult; state: SearchState; loading: boolean; writes: boolean; requirement: PickOption | null; shortlisted: Shortlisted;
  onRequirement: (r: PickOption | null) => void; onShortlist: (c: CandidateCard) => void; narrow: (c: Partial<SearchState>) => void; page: (offset: number) => void;
  selected: Map<string, ShareCandidate>; onSelect: (c: CandidateCard, on: boolean) => void; bulkBar: React.ReactNode; // pob-019 T12
  sorts: { key: SortKey; label: string }[]; onSort: (sort: SortKey) => void; // hrc-019 S10
  exportBar?: React.ReactNode; // hrc-020: Export CSV / Excel for holders of `candidates.export`
}) {
  const expanded = result.terms.filter((t) => t.also.length || t.skill.name.toLowerCase() !== t.term.toLowerCase());
  const facetButton = (label: string, count: number, onClick?: () => void, pressed = false) => count > 0 && ( // QA-04: empty rows are noise
    <li key={label}>
      {onClick ? (
        <button type="button" className="btn ghost small" aria-pressed={pressed} onClick={onClick} style={{ width: "100%", justifyContent: "space-between" }}>
          <span>{label}</span><span>{count}</span>
        </button>
      ) : (
        <span style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", fontSize: 13 }} className="muted"><span>{label}</span><span>{count}</span></span>
      )}
    </li>
  );
  const facet = (title: string, items: React.ReactNode[]) => items.some(Boolean) && (
    <div>
      <h3 style={{ fontSize: 15, margin: "0 0 4px" }}>{title}</h3>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4 }}>{items}</ul>
    </div>
  );
  const header = (
      <div>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <div role="status"><h2 style={{ fontSize: 22, margin: 0 }}>{result.total === 1 ? "1 candidate found" : `${result.total} candidates found`}</h2></div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="find-sort" style={{ fontSize: 14 }}>Sort by</label>
            <select id="find-sort" value={state.sort} onChange={(e) => onSort(e.target.value as SortKey)}>
              {sorts.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
        {expanded.length > 0 && (
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
            {expanded.map((t) => `${t.term} → ${[t.skill.name, ...t.also].join(", ")}`).join("; ")}
          </p>
        )}
        {loading && <p className="muted" role="status" style={{ margin: "4px 0 0", fontSize: 13 }}>Updating results…</p>}
        {exportBar && <div style={{ marginTop: 8 }}>{exportBar}</div>}
      </div>
  );
  const sectionProps = { "aria-label": "Search results", "aria-busy": loading, style: { display: "grid", gap: 12 } } as const;
  if (result.total === 0) { // QA-01: nothing to refine or shortlist; rec-014 FT3: the API says why a resume search matched nothing
    return <section {...sectionProps}>{header}<p className="muted">{result.notice ?? "No candidates match. Remove a skill or a filter to see more."}</p></section>;
  }
  return (
    <section {...sectionProps}>
      {header}
      {writes && (
        <div className="action-card" style={{ gap: 6 }}>
          <SearchableSelect label="Shortlist into requirement" noun="requirement" search={requirementSearch} onChange={onRequirement} initial={requirement} />
          <span className="muted" style={{ fontSize: 13 }}>
            {requirement ? `Shortlist adds a candidate to ${requirement.label} as Shortlisted; or select candidates to shortlist, share or assign a task in one go.`
              : "Select candidates to assign them a task; choose one of your open requirements to shortlist them into it or share their profiles."}
          </span>
          {bulkBar}
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
          {result.items.length === 0 ? ( // QA-07: a hand-edited offset past the end
            <p className="muted">No candidates on this page. <button type="button" className="btn secondary small" onClick={() => page(0)}>Go to the first page</button></p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
              {result.items.map((c) => (
                <Card key={c.id} c={c} writes={writes} requirement={requirement} shortlisted={shortlisted[c.id]} onShortlist={onShortlist}
                  selected={writes ? selected.has(c.id) : null} onSelect={(on) => onSelect(c, on)} />
              ))}
            </ul>
          )}
          {result.total > PAGE_SIZE && result.items.length > 0 && (
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
