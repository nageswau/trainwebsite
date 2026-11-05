"use client";
import { type FormEvent, type ReactNode, useMemo, useState } from "react";

import { DetailList, multiline } from "@/components/BdmOrganizationProfileDetails";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { type Company, COMPANIES_URL, contextBody, contextOf, type ContextDraft, isCompanyBody } from "@/lib/recruiterCompanies";
import { skillSearch } from "@/lib/recruiterSkills";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const NONE = "None recorded";
const CITY_REQUIRED = "Enter a city for every branch.";
const list = (items: string[] | undefined): ReactNode => (items?.length ? items.join(", ") : NONE);

// pob-003 (DEC-SCOPE-406 D1-D3): what the company sells and hires for, and where it has branches. The view reads the company the page
// already has; Edit (the assigned recruiter / super admin -- `permissions.can_edit`) sends only the changed fields through the company
// PATCH, and the page re-renders from the company it returns. The server re-checks everything (lists, sizes, active skills).
export default function RecruiterCompanyBusiness({ company, onSaved }: { company: Company; onSaved: (c: Company, saved: boolean) => void }) {
  const [draft, setDraft] = useState<ContextDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [picker, setPicker] = useState(0); // re-mounts the skill picker after each pick
  const focus = useFocusAfterRender();
  const original = useMemo(() => contextOf(company), [company]);
  const search = useMemo(() => skillSearch(""), []);
  const editId = `company-${company.id}-context-edit`;
  const titleId = `company-${company.id}-context`;
  const set = (next: Partial<ContextDraft>) => setDraft((d) => (d ? { ...d, ...next } : d));

  function close() {
    setDraft(null);
    setFailure(null);
    focus(editId);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    if (draft.branches.some((b) => !b.city.trim())) return setFailure(CITY_REQUIRED);
    const body = contextBody(draft, original);
    if (Object.keys(body).length === 0) {
      onSaved(company, false);
      return close();
    }
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${COMPANIES_URL}/${company.id}`, "PATCH", body);
    setBusy(false);
    if (outcome.ok && isCompanyBody(outcome.data)) {
      onSaved(outcome.data.company, true);
      close();
    } else setFailure(outcome.ok ? "Unable to save the business context." : outcome.message);
  }

  const branches = company.branch_locations ?? [];
  const rows: [string, ReactNode][] = [
    ["Products and services", company.products_services ? multiline(company.products_services) : NONE],
    ["Departments hiring", list(company.departments_hiring)],
    ["Likely skill demand", list(company.skill_demand?.map((s) => `${s.name}${s.active ? "" : " (inactive)"}`))],
    ["Hiring locations", list(company.hiring_locations)],
    ["Target roles", list(company.target_roles)],
    ["Branch locations", branches.length ? (
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {branches.map((b, i) => <li key={i}>{[b.city, b.state, b.country].filter(Boolean).join(", ")}</li>)}
      </ul>
    ) : NONE],
  ];

  return (
    <section className="action-card wide" aria-labelledby={titleId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={titleId}>Business context</h3>
        {company.permissions.can_edit && !draft && (
          <button id={editId} type="button" className="btn secondary small" aria-label="Edit business context" onClick={() => setDraft(original)}>
            Edit
          </button>
        )}
      </div>
      {!draft ? (
        <DetailList rows={rows} />
      ) : (
        <form className="form" onSubmit={(e) => void save(e)} noValidate>
          <div className="field">
            <label htmlFor="context-products">Products and services</label>
            <textarea id="context-products" rows={3} maxLength={2000} value={draft.products} onChange={(e) => set({ products: e.target.value })} />
          </div>
          {([["departments", "Departments hiring"], ["locations", "Hiring locations"], ["roles", "Target roles"]] as const).map(([key, label]) => (
            <div className="field" key={key}>
              <label htmlFor={`context-${key}`}>{label}</label>
              <input id={`context-${key}`} value={draft[key]} onChange={(e) => set({ [key]: e.target.value })} aria-describedby={`context-${key}-hint`} />
              <small id={`context-${key}-hint`} className="muted">Separate several with commas (up to 20).</small>
            </div>
          ))}
          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend>Likely skill demand</legend>
            {draft.skills.length > 0 ? (
              <ul style={{ display: "flex", flexWrap: "wrap", gap: 8, listStyle: "none", padding: 0, margin: 0 }}>
                {draft.skills.map((s) => (
                  <li key={s.id} className="badge">
                    {s.name}{s.active ? "" : " (inactive)"}{" "}
                    <button type="button" className="btn ghost small" aria-label={`Remove skill ${s.name}`} onClick={() => set({ skills: draft.skills.filter((x) => x.id !== s.id) })}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted" style={{ margin: 0 }}>No skills added.</p>
            )}
            <SearchableSelect key={picker} label="Add a skill" noun="skill" search={search} onChange={(option) => {
              if (option && !draft.skills.some((s) => s.id === option.id)) set({ skills: [...draft.skills, { id: option.id, name: option.label, active: true }] });
              setPicker((n) => n + 1);
            }} />
          </fieldset>
          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend>Branch locations</legend>
            {draft.branches.map((b, i) => (
              <div key={i} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                {(["city", "state", "country"] as const).map((part) => (
                  <div className="field" key={part} style={{ flex: "1 1 140px", margin: 0 }}>
                    <label htmlFor={`branch-${i}-${part}`}>
                      <span className="visually-hidden">Branch {i + 1} </span>
                      {part === "city" ? "City" : part === "state" ? "State" : "Country"}
                    </label>
                    <input id={`branch-${i}-${part}`} maxLength={120} value={b[part]} required={part === "city"}
                      onChange={(e) => set({ branches: draft.branches.map((x, j) => (j === i ? { ...x, [part]: e.target.value } : x)) })} />
                  </div>
                ))}
                <button type="button" className="btn secondary small" aria-label={`Remove branch ${i + 1}`} onClick={() => set({ branches: draft.branches.filter((_, j) => j !== i) })}>
                  Remove
                </button>
              </div>
            ))}
            {draft.branches.length < 50 && (
              <div>
                <button type="button" className="btn secondary small" onClick={() => set({ branches: [...draft.branches, { city: "", state: "", country: "" }] })}>
                  Add branch
                </button>
              </div>
            )}
          </fieldset>
          {failure && <p className="form-error" role="alert">{failure}</p>}
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy} aria-label="Save business context">
              {busy ? "Saving…" : "Save"}
            </button>
            <button type="button" className="btn secondary small" onClick={close} disabled={busy}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
