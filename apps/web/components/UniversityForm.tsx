"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import UniversityMatchList from "@/components/UniversityMatchList";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { formOptional as optional, formText as text } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import {
  COURSE_LEVELS,
  countrySearch,
  duplicatesUrl,
  INSTITUTION_TYPES,
  OWNERSHIP_TYPES,
  POTENTIALS,
  PRIORITIES,
  RANKING_SYSTEMS,
  RELATIONSHIP_STRENGTHS,
  RELATIONSHIPS,
  type University,
  UNIVERSITIES_URL,
  universityDuplicate,
  type UniversityDuplicate,
  type UniversityMatchPage,
  universityPath,
  universityUrl,
} from "@/lib/universities";

// upc-003 (AC1): add or edit a university's master record (EVID-020 §1, minus the contact rows that upc-006 owns). A 422 lands on its
// field; anything else is one alert. The entry is never cleared on an error, and a double click sends one request.
// upc-004 (§26): while the name or country is being entered, the master is searched for the same name + country (advisory; UD6). A save
// into one is a 409 with the same panel; a head / super_admin may add it anyway with a reason (UD2).
type RankingRow = { key: number; system: string; other_name: string; year: string; rank: string };
type Errors = Record<string, string>;
const MAX_RANKINGS = 10;
const SEARCH_DELAY_MS = 400;


function fieldErrors(detail: unknown): Errors | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const errors: Errors = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const [where, field] = item?.loc ?? [];
    if (where !== "body" || typeof field !== "string") return null;
    errors[field] = errors[field] ? `${errors[field]}; ${detailMessage([item])}` : detailMessage([item]);
  }
  return errors;
}

function ErrorText({ id, error }: { id?: string; error?: string }) {
  return error ? <p className="field-error" id={id} style={{ color: "var(--red)", fontSize: 13, margin: "4px 0 0" }}>{error}</p> : null;
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      <ErrorText id={`${id}-error`} error={error} />
    </div>
  );
}

function Select({ id, name, value, words, blank, invalid }: { id: string; name: string; value?: string | null; words: Record<string, string>; blank?: string; invalid?: boolean }) {
  return (
    <select id={id} name={name} defaultValue={value ?? ""} aria-invalid={invalid || undefined} aria-describedby={invalid ? `${id}-error` : undefined}>
      {blank !== undefined && <option value="">{blank}</option>}
      {Object.entries(words).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
    </select>
  );
}

export default function UniversityForm({ university }: { university?: University }) {
  const router = useRouter();
  const editing = university !== undefined;
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [message, setMessage] = useState<string | null>(null);
  const nextKey = useRef(university?.rankings.length ?? 0);
  const [rankings, setRankings] = useState<RankingRow[]>(() =>
    (university?.rankings ?? []).map((r, key) => ({ key, system: r.system, other_name: r.other_name ?? "", year: String(r.year), rank: r.rank })));
  const [name, setName] = useState(university?.name ?? "");
  const [countryId, setCountryId] = useState(university?.country.id ?? "");
  const [existing, setExisting] = useState<UniversityMatchPage | null>(null);
  const [duplicate, setDuplicate] = useState<UniversityDuplicate | null>(null);
  const focus = useFocusAfterRender();

  useEffect(() => {
    const unchanged = editing && name.trim() === university.name && countryId === university.country.id;
    if (name.trim().length < 2 || !countryId || unchanged) {
      setExisting(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(duplicatesUrl(name.trim(), countryId, university?.id), { signal: controller.signal })
        .then((r) => (r.ok ? (r.json() as Promise<UniversityMatchPage>) : null))
        .then((page) => setExisting(page && page.total > 0 ? page : null))
        .catch(() => {}); // advisory: the save re-checks on the server
    }, SEARCH_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [name, countryId, editing, university]);

  const updateRanking = (key: number, change: Partial<RankingRow>) => setRankings((rows) => rows.map((r) => (r.key === key ? { ...r, ...change } : r)));
  const invalid = (name: string) => (errors[name] ? { "aria-invalid": true as const, "aria-describedby": `uni-${name}-error` } : {});

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    const form = new FormData(event.currentTarget);
    const body = {
      name: text(form, "name"), country_id: text(form, "country_id"), city: text(form, "city"),
      institution_type: text(form, "institution_type"), ownership_type: optional(form, "ownership_type"), state_region: optional(form, "state_region"),
      website: optional(form, "website"), course_levels: form.getAll("course_levels").map(String),
      popular_programs: text(form, "popular_programs").split(",").map((p) => p.trim()).filter(Boolean),
      international_office: optional(form, "international_office"), existing_relationship: optional(form, "existing_relationship"),
      priority: optional(form, "priority"), partnership_potential: optional(form, "partnership_potential"),
      relationship_strength: optional(form, "relationship_strength"),
      overview: text(form, "overview"), eligibility: text(form, "eligibility"),
      rankings: rankings.map((r) => ({ system: r.system, other_name: r.system === "Other" ? r.other_name.trim() || null : null, year: Number(r.year), rank: r.rank.trim() })),
      ...(duplicate?.can_override ? { duplicate_reason: text(form, "duplicate_reason") } : {}),
    };
    sending.current = true;
    setBusy(true);
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(editing ? universityUrl(university.id) : UNIVERSITIES_URL, {
        method: editing ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
    } catch {
      sending.current = false;
      setBusy(false);
      setMessage(NOT_COMPLETED);
      return;
    }
    const data = await response.json().catch(() => null);
    if (response.ok && data?.university?.id) {
      router.push(universityPath(data.university.id));
      router.refresh();
      return;
    }
    sending.current = false;
    setBusy(false);
    const found = response.status === 409 ? universityDuplicate(data?.detail) : null;
    if (found) {
      setErrors({});
      setDuplicate(found);
      focus("uni-duplicate");
      return;
    }
    const mapped = response.status === 422 ? fieldErrors(data?.detail) : null;
    setErrors(mapped ?? {});
    setMessage(mapped ? "Check the highlighted fields." : detailMessage(data?.detail, "The university could not be saved. Try again."));
  }

  const u = university;
  return (
    <form className="action-card wide" onSubmit={submit} aria-busy={busy}>
      {message && <p role="alert" className="notice" style={{ marginTop: 0 }}>{message}</p>}
      <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 12 }}>
        <legend className="visually-hidden">University details</legend>
        <Field id="uni-name" label="University name (required)" error={errors.name}>
          <input id="uni-name" name="name" required maxLength={200} defaultValue={u?.name ?? ""} onChange={(e) => { setName(e.target.value); setDuplicate(null); }} {...invalid("name")} />
        </Field>
        <div>
          <SearchableSelect id="uni-country" name="country_id" label="Country (required)" noun="country" required search={countrySearch}
            onChange={(option) => { setCountryId(option?.id ?? ""); setDuplicate(null); }}
            initial={u ? { id: u.country.id, label: u.country.name, detail: [u.country.iso2, u.country.region].filter(Boolean).join(" · ") } : null} />
          <ErrorText error={errors.country_id} />
        </div>
        {existing && !duplicate && (
          <div role="status" className="notice">
            <strong>Already in the University Master</strong> — check these before adding another one.
            <UniversityMatchList matches={existing.items} total={existing.total} linkable />
          </div>
        )}
        {duplicate && (
          <div role="alert" className="form-error">
            <strong id="uni-duplicate" tabIndex={-1}>{duplicate.message}</strong>
            <UniversityMatchList matches={duplicate.matches} total={duplicate.total} linkable />
            {duplicate.can_override ? (
              <Field id="uni-duplicate_reason" label="Reason for adding it anyway (required)" error={errors.duplicate_reason}>
                <textarea id="uni-duplicate_reason" name="duplicate_reason" rows={2} required minLength={10} maxLength={500}
                  aria-describedby="uni-duplicate_reason-hint" {...invalid("duplicate_reason")} />
                <small id="uni-duplicate_reason-hint" className="muted">At least 10 characters. It is kept in the audit log.</small>
              </Field>
            ) : (
              <p style={{ margin: 0 }}>Ask your partnership head to add it if this is a different university.</p>
            )}
          </div>
        )}
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
          <Field id="uni-city" label="City (required)" error={errors.city}>
            <input id="uni-city" name="city" required maxLength={120} defaultValue={u?.city ?? ""} {...invalid("city")} />
          </Field>
          <Field id="uni-state_region" label="State / region" error={errors.state_region}>
            <input id="uni-state_region" name="state_region" maxLength={120} defaultValue={u?.state_region ?? ""} {...invalid("state_region")} />
          </Field>
          <Field id="uni-institution_type" label="Institution type" error={errors.institution_type}>
            <Select id="uni-institution_type" name="institution_type" value={u?.institution_type ?? "university"} words={INSTITUTION_TYPES} invalid={!!errors.institution_type} />
          </Field>
          <Field id="uni-ownership_type" label="Public / private" error={errors.ownership_type}>
            <Select id="uni-ownership_type" name="ownership_type" value={u?.ownership_type} words={OWNERSHIP_TYPES} blank="Not recorded" invalid={!!errors.ownership_type} />
          </Field>
          <Field id="uni-website" label="Website" error={errors.website}>
            <input id="uni-website" name="website" maxLength={300} inputMode="url" placeholder="abc.ac.uk" defaultValue={u?.website ?? ""} {...invalid("website")} />
          </Field>
          <Field id="uni-existing_relationship" label="Existing relationship" error={errors.existing_relationship}>
            <Select id="uni-existing_relationship" name="existing_relationship" value={u?.existing_relationship} words={RELATIONSHIPS} blank="Not recorded" />
          </Field>
          <Field id="uni-priority" label="Priority" error={errors.priority}>
            <Select id="uni-priority" name="priority" value={u?.priority} words={Object.fromEntries(PRIORITIES.map((p) => [p, p]))} blank="Not set" />
          </Field>
          <Field id="uni-partnership_potential" label="Partnership potential" error={errors.partnership_potential}>
            <Select id="uni-partnership_potential" name="partnership_potential" value={u?.partnership_potential} words={POTENTIALS} blank="Not set" />
          </Field>
          <Field id="uni-relationship_strength" label="Relationship strength" error={errors.relationship_strength}>
            <Select id="uni-relationship_strength" name="relationship_strength" value={u?.relationship_strength} words={RELATIONSHIP_STRENGTHS} blank="Not assessed" />
          </Field>
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }} aria-describedby={errors.course_levels ? "uni-course_levels-error" : undefined}>
          <legend style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>Course levels offered</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
            {COURSE_LEVELS.map((level) => (
              <label key={level} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" name="course_levels" value={level} defaultChecked={u?.course_levels.includes(level)} /> {level}
              </label>
            ))}
          </div>
          <ErrorText id="uni-course_levels-error" error={errors.course_levels} />
        </fieldset>
        <Field id="uni-popular_programs" label="Popular programme areas" error={errors.popular_programs}>
          <input id="uni-popular_programs" name="popular_programs" maxLength={1700} placeholder="IT, Business, Engineering, Healthcare"
            defaultValue={u?.popular_programs.join(", ") ?? ""} aria-describedby="uni-programs-hint" {...invalid("popular_programs")} />
          <small id="uni-programs-hint" className="muted">Separate areas with commas (up to 20).</small>
        </Field>
        <Field id="uni-international_office" label="International office contact" error={errors.international_office}>
          <textarea id="uni-international_office" name="international_office" rows={2} maxLength={1000} defaultValue={u?.international_office ?? ""} {...invalid("international_office")} />
        </Field>
        <Field id="uni-overview" label="Overview (shown in the public catalogue once published)" error={errors.overview}>
          <textarea id="uni-overview" name="overview" rows={4} maxLength={5000} defaultValue={u?.overview ?? ""} {...invalid("overview")} />
        </Field>
        <Field id="uni-eligibility" label="Eligibility" error={errors.eligibility}>
          <textarea id="uni-eligibility" name="eligibility" rows={2} maxLength={5000} defaultValue={u?.eligibility ?? ""} {...invalid("eligibility")} />
        </Field>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>Rankings</legend>
          {rankings.length === 0 && <p className="muted" style={{ margin: "0 0 8px" }}>No rankings recorded.</p>}
          {rankings.map((r, i) => (
            <div key={r.key} style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", alignItems: "end", marginBottom: 8 }}>
              <div className="field">
                <label htmlFor={`rk-${r.key}-system`}>Ranking {i + 1} system</label>
                <select id={`rk-${r.key}-system`} value={r.system} onChange={(e) => updateRanking(r.key, { system: e.target.value })}>
                  {RANKING_SYSTEMS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              {r.system === "Other" && (
                <div className="field">
                  <label htmlFor={`rk-${r.key}-name`}>Ranking {i + 1} name</label>
                  <input id={`rk-${r.key}-name`} maxLength={80} required value={r.other_name} onChange={(e) => updateRanking(r.key, { other_name: e.target.value })} />
                </div>
              )}
              <div className="field">
                <label htmlFor={`rk-${r.key}-year`}>Ranking {i + 1} year</label>
                <input id={`rk-${r.key}-year`} type="number" min={1900} max={2100} required value={r.year} onChange={(e) => updateRanking(r.key, { year: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor={`rk-${r.key}-rank`}>Ranking {i + 1} rank</label>
                <input id={`rk-${r.key}-rank`} maxLength={20} required placeholder="45 or 201-250" value={r.rank} onChange={(e) => updateRanking(r.key, { rank: e.target.value })} />
              </div>
              <button type="button" className="btn secondary small" aria-label={`Remove ranking ${i + 1}`} onClick={() => setRankings((rows) => rows.filter((x) => x.key !== r.key))}>Remove</button>
            </div>
          ))}
          <ErrorText error={errors.rankings} />
          {rankings.length < MAX_RANKINGS && (
            <button type="button" className="btn secondary small"
              onClick={() => setRankings((rows) => [...rows, { key: nextKey.current++, system: "QS", other_name: "", year: String(new Date().getFullYear()), rank: "" }])}>
              Add ranking
            </button>
          )}
        </fieldset>
      </fieldset>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
        <button className="btn" type="submit" disabled={busy || (duplicate !== null && !duplicate.can_override)}>
          {busy ? "Saving…" : duplicate?.can_override ? (editing ? "Save anyway" : "Add anyway") : editing ? "Save changes" : "Add university"}
        </button>
        <a className="btn secondary" href={editing ? universityPath(university.id) : "/partnership/universities"}>Cancel</a>
      </div>
    </form>
  );
}
