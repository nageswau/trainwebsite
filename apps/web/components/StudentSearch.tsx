import Link from "next/link";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { STUDENT_KINDS, STUDENT_SEARCH_MAX, type StudentKind, type StudentSearchFilters, type StudentSearchResult } from "@/lib/studentSearch";

export type ProgramOption = { id: string; title: string };

// nehn-041 (DEC-SCOPE-291 S6/S10): the Student search -- a GET form (refresh, back and a shared link keep the search) and one group of
// result cards per kind the caller may see. A card opens the student's page in one click; a kind with no page for this caller (a school
// student for the Super Admin) names the school instead. `result` is null when nothing was searched yet, the read failed or the search
// was refused; the form stays so it can be corrected.
export default function StudentSearch({ base, filters, kinds, programs, result, error }: {
  base: string; filters: StudentSearchFilters; kinds: StudentKind[]; programs: ProgramOption[] | null; result: StudentSearchResult | null; error: string;
}) {
  const groups = result ? STUDENT_KINDS.filter((k) => result.groups[k.value]) : [];
  const total = groups.reduce((n, k) => n + (result?.groups[k.value]?.items.length ?? 0), 0);
  return (
    <div className="action-card">
      <form method="get" action={base} role="search" aria-label="Student search" className="analytics-form">
        <div className="field" style={{ margin: 0, flex: "1 1 260px" }}>
          <label htmlFor="student-search-q">Student ID, name, phone, email or course</label>
          <input id="student-search-q" className="input" type="search" name="q" defaultValue={filters.q} maxLength={STUDENT_SEARCH_MAX}
            placeholder="e.g. 3FA9C21B, 98765 43210" autoComplete="off" />
        </div>
        {kinds.length > 1 && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="student-search-type">Type</label>
            <select id="student-search-type" name="type" defaultValue={filters.type}>
              <option value="">All types</option>
              {STUDENT_KINDS.filter((k) => kinds.includes(k.value)).map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
          </div>
        )}
        {programs && programs.length > 0 && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="student-search-program">IT program</label>
            <select id="student-search-program" name="program" defaultValue={filters.program}>
              <option value="">Any program</option>
              {programs.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </div>
        )}
        <button className="btn" type="submit">Search</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {result && total === 0 && <p className="empty" role="status">No students you can see match “{result.q}”.</p>}
      {total > 0 && (
        <div style={{ display: "grid", gap: 20, marginTop: 16 }}>
          {groups.map(({ value, label }) => {
            const group = result!.groups[value]!;
            return (
              <section key={value} aria-labelledby={`student-search-${value}`}>
                <h3 id={`student-search-${value}`} style={{ fontSize: 16, margin: "0 0 8px" }}>
                  {label} ({group.items.length}{group.more ? "+" : ""})
                </h3>
                {group.items.length === 0 ? (
                  <p className="muted" style={{ margin: 0 }}>No matches</p>
                ) : (
                  <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(min(260px, 100%), 1fr))" }}>
                    {group.items.map((hit) => (
                      <li key={hit.id} className="panel" style={{ padding: 14, minWidth: 0 }}>
                        <strong style={{ display: "block", overflowWrap: "anywhere" }}>
                          {hit.href ? <Link href={hit.href} style={LINK_STYLE}>{hit.label || "Unnamed student"}</Link> : hit.label || "Unnamed student"}
                        </strong>
                        {hit.code && <div style={{ fontSize: 13 }}>Student ID {hit.code}</div>}
                        {hit.detail && <div className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>{hit.detail}</div>}
                      </li>
                    ))}
                  </ul>
                )}
                {group.more && <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>Showing the first {group.items.length} — refine your search.</p>}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
