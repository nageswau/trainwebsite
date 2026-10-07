import LocalTime from "@/components/LocalTime";
import { milestoneKind, statusText, type Milestones } from "@/lib/leadHandover";

/** tel-018 (T4, T5): the linked student and what happened next -- IT enrolments, overseas applications and visa cases, read live and
 *  read only -- with the Converted badge once the system has recorded the conversion. */
export default function LeadMilestones({ milestones, status }: { milestones: Milestones; status: string }) {
  const { student, items } = milestones;
  return (
    <section aria-labelledby="lead-milestones-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <h3 id="lead-milestones-heading" style={{ margin: 0 }}>Student and milestones</h3>
        {status === "converted" && <span className="badge">Converted</span>}
      </div>
      {!student ? (
        <p className="muted" style={{ fontSize: 13 }}>No student account is linked yet.</p>
      ) : (
        <>
          <p style={{ margin: "6px 0 0", overflowWrap: "anywhere" }}>Linked student: <strong>{student.full_name} ({student.email})</strong></p>
          {items.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No enrolment or application yet.</p>
          ) : (
            <ul aria-label="Milestones" style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 4 }}>
              {items.map((m, i) => (
                <li key={`${m.kind}-${i}`}>
                  <strong>{milestoneKind(m.kind)}</strong> · {m.label} — {statusText(m.status)}
                  <span className="muted" style={{ fontSize: 13 }}>{m.reference ? ` · ${m.reference}` : ""} · <LocalTime value={m.at} /></span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
