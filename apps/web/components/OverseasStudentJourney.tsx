import type { StudentJourney } from "@/lib/overseasStudent360";

const STATE = { done: "Done", current: "Current", upcoming: "Not yet" } as const;
const GLYPH = { done: "✓", current: "•", upcoming: "–" } as const;

/** ccrm-017 (DEC-SCOPE-258): the student's derived journey stage on the 360 -- AGN-015's step-tracker styling, the state always as text
 *  (never colour alone), separate from each application's own status. */
export default function OverseasStudentJourney({ journey }: { journey: StudentJourney }) {
  const { application } = journey;
  return (
    <div className="card">
      <h2>Journey stage: {journey.label}</h2>
      <ol className="jny-steps" aria-label="Student journey">
        {journey.steps.map((s) => (
          <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
            <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
            <span className="jny-name">{s.label}</span>
            <span className="jny-state">{STATE[s.state]}</span>
          </li>
        ))}
      </ol>
      {journey.note && <p className="muted" style={{ margin: "0 0 4px" }}>{journey.note}</p>}
      {application && (
        <p className="muted" style={{ margin: 0 }}>
          Furthest application: {application.application_code ?? "No code"} · {application.university}
        </p>
      )}
    </div>
  );
}
