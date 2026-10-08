import Link from "next/link";

import { type Filters, INSTITUTION_TYPES, POTENTIALS, PRIORITIES, REGIONS, UNIVERSITIES_PATH } from "@/lib/universities";

// upc-003: the list's filters as a plain GET form -- the URL holds them, so Back, Refresh and a shared link all keep the view, and it
// works without client JS. Every filter only narrows; the API applies the same names.
function Choice({ id, name, text, value, options }: { id: string; name: string; text: string; value?: string; options: [string, string][] }) {
  return (
    <div className="field">
      <label htmlFor={id}>{text}</label>
      <select id={id} name={name} defaultValue={value ?? ""}>
        <option value="">Any</option>
        {options.map(([key, word]) => <option key={key} value={key}>{word}</option>)}
      </select>
    </div>
  );
}

export default function UniversityFilters({ filters, isManager }: { filters: Filters; isManager: boolean }) {
  const managerOptions: [string, string][] = [...(isManager ? [["me", "Assigned to me"] as [string, string]] : []), ["none", "Unassigned"]];
  return (
    <form className="action-card wide" method="get" action={UNIVERSITIES_PATH} role="search" aria-label="Filter universities">
      <div className="form-grid" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <div className="field">
          <label htmlFor="uf-q">Search</label>
          <input id="uf-q" name="q" type="search" maxLength={200} defaultValue={filters.q ?? ""} placeholder="Name, code or city" />
        </div>
        <Choice id="uf-region" name="region" text="Region" value={filters.region} options={REGIONS.map((r) => [r, r])} />
        <Choice id="uf-type" name="institution_type" text="Institution type" value={filters.institution_type} options={Object.entries(INSTITUTION_TYPES)} />
        <Choice id="uf-priority" name="priority" text="Priority" value={filters.priority} options={PRIORITIES.map((p) => [p, p])} />
        <Choice id="uf-potential" name="partnership_potential" text="Potential" value={filters.partnership_potential} options={Object.entries(POTENTIALS)} />
        <Choice id="uf-manager" name="manager" text="Manager" value={filters.manager} options={managerOptions} />
        <Choice id="uf-visibility" name="visibility" text="Catalogue" value={filters.visibility} options={[["public", "Public"], ["internal", "Internal"]]} />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 12 }}>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" name="include_inactive" value="true" defaultChecked={filters.include_inactive === "true"} /> Include inactive
        </label>
        <button className="btn small" type="submit">Apply filters</button>
        <Link className="btn secondary small" href={UNIVERSITIES_PATH}>Clear</Link>
      </div>
    </form>
  );
}
