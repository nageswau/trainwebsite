import type { SchoolKpi } from "@/lib/types";

// ENH-016 (School CRM.md §1): the KPI board /school/dashboard already computes, grouped so the first screen reads top-down.
// An untracked KPI says so in words -- never a fabricated 0 (DATA_MODEL.md §8).
const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Students", keys: ["total_students", "grade_8", "grade_9", "grade_10", "grade_11", "grade_12"] },
  { title: "Career & assessment", keys: ["career_guidance_completed", "psychometric_tests_completed", "individual_counselling_completed"] },
  { title: "Skills & languages", keys: ["ielts_training", "sat_preparation", "foreign_language_students", "digital_portfolios_created"] },
  { title: "Global pathway", keys: ["students_in_global_education_pathway", "university_shortlisting", "applications_in_progress", "offers_received", "visa_applications", "students_admitted", "internships"] },
];

export default function SchoolKpiBoard({ kpis }: { kpis: SchoolKpi[] }) {
  const byKey = new Map(kpis.map((k) => [k.key, k]));
  const groups = GROUPS.map((g) => ({ ...g, items: g.keys.map((key) => byKey.get(key)).filter((k): k is SchoolKpi => Boolean(k)) })).filter((g) => g.items.length > 0);
  return (
    <div className="card">
      <h2>School at a glance</h2>
      {groups.length === 0 ? (
        <p className="muted">No figures to show yet.</p>
      ) : (
        groups.map((group) => (
          <section key={group.title} aria-label={group.title} className="kpi-group">
            <h3>{group.title}</h3>
            <dl className="kpi-grid">
              {group.items.map((k) => (
                <div className="kpi-tile" key={k.key}>
                  <dt>{k.label}</dt>
                  {k.tracked && k.value !== null ? (
                    <dd className="kpi-value">{k.value.toLocaleString("en-IN")}</dd>
                  ) : (
                    <dd>
                      <span className="badge">Not tracked yet</span>
                      {k.note && <span className="kpi-note muted">{k.note}</span>}
                    </dd>
                  )}
                </div>
              ))}
            </dl>
          </section>
        ))
      )}
    </div>
  );
}
