import { monthLabel, type TargetSheet } from "@/lib/bdmTargets";

/** bdm-016: the BDM's "Monthly targets" card on My Day -- each KPI with a target this month as achieved / target (percent). `null` means
 *  the read failed: My Day still renders. */
export default function BdmTargetsCard({ sheet }: { sheet: TargetSheet | null }) {
  const set = sheet?.kpis.filter((k) => k.target !== null) ?? [];
  return (
    <section className="action-card wide" aria-labelledby="my-day-targets">
      <h3 id="my-day-targets">{sheet ? `Monthly targets — ${monthLabel(sheet.month)}` : "Monthly targets"}</h3>
      {sheet === null ? (
        <p className="muted">Unable to load your targets right now.</p>
      ) : set.length === 0 ? (
        <p className="muted">No targets set for this month yet.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "grid", gap: 4 }}>
          {set.map((k) => (
            <li key={k.key}>
              {k.label} — {k.tracked ? `${k.achieved ?? "—"} / ${k.target}${k.percent === null ? "" : ` (${k.percent}%)`}` : `target ${k.target} (not tracked)`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
