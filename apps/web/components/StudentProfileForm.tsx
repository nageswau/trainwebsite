"use client";

import { FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import {
  COURSE_LEVELS, CURRENCIES, ENGLISH_SCORE_RANGES, ENGLISH_TESTS, MAX_ENGLISH_TESTS, MAX_PREFERRED_COUNTRIES, MAX_QUALIFICATIONS, QUALIFICATION_LEVELS,
  SCORE_TYPES, STUDY_MODES, TEST_STATUSES, emptyEnglishTest, emptyQualification, fieldPlace, toSaveBody,
  type CountryOption, type EnglishTest, type Qualification, type StudentProfile, type StudentProfileResponse,
} from "@/lib/studentProfile";

const YEAR_MAX = new Date().getFullYear() + 6;

/** A refused save in words: each 422 item with where it is ("Qualification 1 · Score: ..."), else the server's own message. */
function refusal(detail: unknown, message: string): string {
  if (!Array.isArray(detail)) return message;
  return detail.map((item: { loc?: unknown; msg?: string }) => [fieldPlace(item?.loc), detailMessage([item])].filter(Boolean).join(": ")).join("; ");
}

// ccrm-007 (DEC-SCOPE-249): the structured overseas student profile, edited by the counselor, the Overseas Admin or the student (P1:
// every field). A save replaces the whole profile (P5) and last write wins (CC5), so the form shows who saved last. On a refusal the
// entries stay; a second save while one is in flight is ignored.
// ccrm-009 (DEC-SCOPE-253 V2): the student 360 shows one `section` per tab -- academic (personal details, academic history, work
// experience), preferences or english. The whole profile is still held and saved, so a save on one tab never clears another's fields.
export type ProfileSection = "academic" | "preferences" | "english";

export default function StudentProfileForm({ initial, url, countries, section }: { initial: StudentProfile; url: string; countries: CountryOption[]; section?: ProfileSection }) {
  const [profile, setProfile] = useState<StudentProfile>(initial);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);

  const set = <K extends keyof StudentProfile>(key: K, value: StudentProfile[K]) => setProfile((p) => ({ ...p, [key]: value }));
  const text = (key: keyof StudentProfile) => ({ value: String(profile[key] ?? ""), onChange: (e: { target: { value: string } }) => set(key, e.target.value as never) });
  const setRow = <T,>(key: "qualifications" | "english_tests", index: number, change: Partial<T>) =>
    setProfile((p) => ({ ...p, [key]: (p[key] as T[]).map((row, i) => (i === index ? { ...row, ...change } : row)) }));
  const removeRow = (key: "qualifications" | "english_tests", index: number) => setProfile((p) => ({ ...p, [key]: (p[key] as unknown[]).filter((_, i) => i !== index) }));

  const shows = (part: ProfileSection) => !section || section === part;
  const choosable = countries.filter((c) => !profile.preferred_countries.some((p) => p.id === c.id));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setMessage(null);
    const outcome = await sendJson(url, "PUT", toSaveBody(profile));
    inFlight.current = false;
    setSaving(false);
    if (!outcome.ok) {
      setMessage({ text: refusal(outcome.detail, outcome.message), failed: true });
      return;
    }
    setProfile((outcome.data as StudentProfileResponse).profile);
    setMessage({ text: "Profile saved.", failed: false });
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Student profile">
      <p className="muted" style={{ margin: 0 }}>
        {profile.exists && profile.updated_by_name ? (
          <>
            Last saved by {profile.updated_by_name}
            {profile.updated_at && (
              <>
                {" "}· <LocalTime value={profile.updated_at} />
              </>
            )}
          </>
        ) : (
          "No profile saved yet."
        )}
      </p>

      {shows("academic") && (
      <>
      <fieldset className="form-section">
        <legend>Personal details</legend>
        <div className="form-grid">
          <div className="field"><label htmlFor="sp-dob">Date of birth</label><input id="sp-dob" type="date" {...text("date_of_birth")} /></div>
          <div className="field"><label htmlFor="sp-nationality">Nationality</label><input id="sp-nationality" maxLength={100} {...text("nationality")} /></div>
          <div className="field"><label htmlFor="sp-city">City</label><input id="sp-city" maxLength={100} {...text("city")} /></div>
          <div className="field"><label htmlFor="sp-state">State</label><input id="sp-state" maxLength={100} {...text("state")} /></div>
          <div className="field"><label htmlFor="sp-passport">Passport number</label><input id="sp-passport" maxLength={20} autoComplete="off" {...text("passport_number")} /></div>
          <div className="field"><label htmlFor="sp-passport-expiry">Passport expiry</label><input id="sp-passport-expiry" type="date" {...text("passport_expiry")} /></div>
        </div>
        <p className="field-help muted">Passport details are shown only to the student, their counselor and the Overseas Admin.</p>
      </fieldset>

      <fieldset className="form-section">
        <legend>Academic history</legend>
        {profile.qualifications.length === 0 && <p className="muted" style={{ margin: 0 }}>No qualifications added.</p>}
        {profile.qualifications.map((q, i) => (
          <QualificationRow key={i} index={i} row={q} onChange={(change) => setRow<Qualification>("qualifications", i, change)} onRemove={() => removeRow("qualifications", i)} />
        ))}
        {profile.qualifications.length < MAX_QUALIFICATIONS ? (
          <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => set("qualifications", [...profile.qualifications, emptyQualification()])}>Add qualification</button>
        ) : (
          <p className="field-help muted">Up to {MAX_QUALIFICATIONS} qualifications.</p>
        )}
      </fieldset>

      <fieldset className="form-section">
        <legend>Work experience</legend>
        <div className="form-grid">
          <div className="field"><label htmlFor="sp-exp-months">Work experience (months)</label><input id="sp-exp-months" type="number" min={0} max={600} step={1} {...text("work_experience_months")} /></div>
          <div className="field"><label htmlFor="sp-exp-details">Work experience details</label><input id="sp-exp-details" maxLength={1000} {...text("work_experience_details")} /></div>
        </div>
      </fieldset>
      </>
      )}

      {shows("preferences") && (

      <fieldset className="form-section">
        <legend>Study preferences</legend>
        <div className="field">
          <span style={{ fontWeight: 800, fontSize: 13 }} id="sp-countries-label">Preferred countries</span>
          {profile.preferred_countries.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>None chosen.</p>
          ) : (
            <ul aria-labelledby="sp-countries-label" style={{ display: "flex", flexWrap: "wrap", gap: 8, listStyle: "none", padding: 0, margin: 0 }}>
              {profile.preferred_countries.map((c) => (
                <li key={c.id} aria-label={c.name} className="badge" style={{ gap: 6, alignItems: "center" }}>
                  {c.name}
                  <button type="button" aria-label={`Remove ${c.name}`} onClick={() => set("preferred_countries", profile.preferred_countries.filter((p) => p.id !== c.id))} style={{ border: 0, background: "none", padding: 0, color: "inherit", fontWeight: 800 }}>×</button>
                </li>
              ))}
            </ul>
          )}
          {profile.preferred_countries.length < MAX_PREFERRED_COUNTRIES && choosable.length > 0 && (
            <select
              aria-label="Add a preferred country"
              value=""
              onChange={(e) => {
                const chosen = countries.find((c) => c.id === e.target.value);
                if (chosen) set("preferred_countries", [...profile.preferred_countries, chosen]);
              }}
            >
              <option value="">Add a country…</option>
              {choosable.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          {profile.preferred_countries.length >= MAX_PREFERRED_COUNTRIES && <p className="field-help muted">Up to {MAX_PREFERRED_COUNTRIES} countries.</p>}
        </div>
        <div className="form-grid">
          <div className="field"><label htmlFor="sp-course">Course or subject</label><input id="sp-course" maxLength={200} {...text("preferred_course")} /></div>
          <div className="field">
            <label htmlFor="sp-level">Study level</label>
            <select id="sp-level" {...text("preferred_level")}><option value="">Not chosen</option>{Object.entries(COURSE_LEVELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </div>
          <div className="field"><label htmlFor="sp-intake">Intake</label><input id="sp-intake" maxLength={40} placeholder="e.g. September 2027" {...text("preferred_intake")} /></div>
          <div className="field">
            <label htmlFor="sp-mode">Study mode</label>
            <select id="sp-mode" {...text("study_mode")}><option value="">Not chosen</option>{Object.entries(STUDY_MODES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </div>
          <div className="field"><label htmlFor="sp-budget-min">Budget from</label><input id="sp-budget-min" type="number" min={0} step="0.01" inputMode="decimal" {...text("budget_min")} /></div>
          <div className="field"><label htmlFor="sp-budget-max">Budget to</label><input id="sp-budget-max" type="number" min={0} step="0.01" inputMode="decimal" {...text("budget_max")} /></div>
          <div className="field">
            <label htmlFor="sp-currency">Budget currency</label>
            <select id="sp-currency" {...text("budget_currency")}><option value="">Not chosen</option>{CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          </div>
        </div>
      </fieldset>
      )}

      {shows("english") && (
      <fieldset className="form-section">
        <legend>English tests</legend>
        {profile.english_tests.length === 0 && <p className="muted" style={{ margin: 0 }}>No English tests added.</p>}
        {profile.english_tests.map((t, i) => (
          <EnglishTestRow key={i} index={i} row={t} onChange={(change) => setRow<EnglishTest>("english_tests", i, change)} onRemove={() => removeRow("english_tests", i)} />
        ))}
        {profile.english_tests.length < MAX_ENGLISH_TESTS ? (
          <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} onClick={() => set("english_tests", [...profile.english_tests, emptyEnglishTest()])}>Add English test</button>
        ) : (
          <p className="field-help muted">Up to {MAX_ENGLISH_TESTS} English tests.</p>
        )}
      </fieldset>
      )}

      {/* Always mounted so screen readers announce the outcome when it arrives; styled only while it has something to say. */}
      <div className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite">{message?.text}</div>
      {/* Never disabled while saving: a disabled button drops keyboard focus; the in-flight guard stops a second save. */}
      <div className="actions"><button className="btn" aria-busy={saving}>{saving ? "Saving…" : "Save profile"}</button></div>
    </form>
  );
}

function RowHeading({ title, onRemove }: { title: string; onRemove: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
      <strong>{title}</strong>
      <button type="button" className="btn ghost small" aria-label={`Remove ${title}`} onClick={onRemove}>Remove</button>
    </div>
  );
}

function QualificationRow({ index, row, onChange, onRemove }: { index: number; row: Qualification; onChange: (c: Partial<Qualification>) => void; onRemove: () => void }) {
  const name = `Qualification ${index + 1}`;
  const id = `sp-q${index}`;
  const input = (key: keyof Qualification) => ({ value: String(row[key] ?? ""), onChange: (e: { target: { value: string } }) => onChange({ [key]: e.target.value || null } as Partial<Qualification>) });
  const cgpa = row.score_type === "cgpa";
  return (
    <div style={{ borderTop: index ? "1px solid var(--line)" : undefined, paddingTop: index ? 12 : 0, display: "grid", gap: 12 }}>
      <RowHeading title={name} onRemove={onRemove} />
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${id}-level`}>Level</label>
          <select id={`${id}-level`} aria-label={`${name} level`} value={row.level} onChange={(e) => onChange({ level: e.target.value })}>
            {Object.entries(QUALIFICATION_LEVELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="field"><label htmlFor={`${id}-name`}>Qualification</label><input id={`${id}-name`} aria-label={`${name} qualification`} maxLength={200} placeholder="e.g. B.Tech Computer Science" {...input("qualification_name")} /></div>
        <div className="field"><label htmlFor={`${id}-inst`}>Institution</label><input id={`${id}-inst`} aria-label={`${name} institution`} maxLength={200} {...input("institution")} /></div>
        <div className="field"><label htmlFor={`${id}-board`}>Board or university</label><input id={`${id}-board`} aria-label={`${name} board or university`} maxLength={200} {...input("board_university")} /></div>
        <div className="field"><label htmlFor={`${id}-year`}>Year completed</label><input id={`${id}-year`} aria-label={`${name} year completed`} type="number" min={1950} max={YEAR_MAX} step={1} {...input("year_completed")} /></div>
        <div className="field">
          <label htmlFor={`${id}-score-type`}>Score type</label>
          <select id={`${id}-score-type`} aria-label={`${name} score type`} {...input("score_type")}><option value="">Not given</option>{Object.entries(SCORE_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </div>
        <div className="field"><label htmlFor={`${id}-score`}>Score</label><input id={`${id}-score`} aria-label={`${name} score`} type="number" min={0} max={cgpa ? 10 : 100} step="0.01" inputMode="decimal" {...input("score")} /></div>
        <div className="field"><label htmlFor={`${id}-backlogs`}>Backlogs</label><input id={`${id}-backlogs`} aria-label={`${name} backlogs`} type="number" min={0} max={99} step={1} {...input("backlogs")} /></div>
      </div>
    </div>
  );
}

/** One English test's fields (ccrm-005 reuses it for a lead's tests, LF3). */
export function EnglishTestRow({ index, row, onChange, onRemove }: { index: number; row: EnglishTest; onChange: (c: Partial<EnglishTest>) => void; onRemove: () => void }) {
  const name = `English test ${index + 1}`;
  const id = `sp-t${index}`;
  const input = (key: keyof EnglishTest) => ({ value: String(row[key] ?? ""), onChange: (e: { target: { value: string } }) => onChange({ [key]: e.target.value || null } as Partial<EnglishTest>) });
  const [low, high] = ENGLISH_SCORE_RANGES[row.test_type] ?? [0, 999];
  return (
    <div style={{ borderTop: index ? "1px solid var(--line)" : undefined, paddingTop: index ? 12 : 0, display: "grid", gap: 12 }}>
      <RowHeading title={name} onRemove={onRemove} />
      {row.expired && <p style={{ margin: 0 }}><span className="status error">Expired</span> <span className="muted">The validity date has passed.</span></p>}
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${id}-type`}>Test</label>
          <select id={`${id}-type`} aria-label={`${name} test`} value={row.test_type} onChange={(e) => onChange({ test_type: e.target.value })}>
            {ENGLISH_TESTS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${id}-status`}>Status</label>
          <select id={`${id}-status`} aria-label={`${name} status`} {...input("status")}><option value="">Not given</option>{Object.entries(TEST_STATUSES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </div>
        <div className="field"><label htmlFor={`${id}-score`}>Overall score</label><input id={`${id}-score`} aria-label={`${name} overall score`} type="number" min={low} max={high} step="0.5" inputMode="decimal" {...input("overall_score")} /></div>
        <div className="field"><label htmlFor={`${id}-date`}>Test date</label><input id={`${id}-date`} aria-label={`${name} test date`} type="date" {...input("test_date")} /></div>
        <div className="field"><label htmlFor={`${id}-valid`}>Valid until</label><input id={`${id}-valid`} aria-label={`${name} valid until`} type="date" {...input("valid_until")} /></div>
        <div className="field"><label htmlFor={`${id}-remarks`}>Remarks</label><input id={`${id}-remarks`} aria-label={`${name} remarks`} maxLength={200} placeholder="e.g. band scores" {...input("remarks")} /></div>
      </div>
    </div>
  );
}
