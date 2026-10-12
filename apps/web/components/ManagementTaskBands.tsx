import type { ReactNode } from "react";

import { groupByBand, type TaskBand } from "@/lib/managementTasks";

// mgmt-028 (MT3): EVID-017 §28's bands as sections -- shared by the management to-do and each staff member's Management tasks. The
// coloured marker is decoration; the band's name carries the meaning. An empty band is not shown.
export default function ManagementTaskBands<T extends { id: string; band: TaskBand | null }>({ items, empty, renderItem }: { items: T[]; empty: string; renderItem: (item: T) => ReactNode }) {
  const groups = groupByBand(items);
  if (groups.length === 0) return <p className="empty" role="status">{empty}</p>;
  return (
    <div style={{ display: "grid", gap: 18 }}>
      {groups.map((group) => (
        <section key={group.band} aria-labelledby={`band-${group.band}`}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span aria-hidden="true">{group.marker}</span>
            <h3 id={`band-${group.band}`} style={{ margin: 0 }}>{group.label} ({group.items.length})</h3>
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
            {group.items.map((item) => <li key={item.id} className="action-card" style={{ display: "grid", gap: 8, overflowWrap: "anywhere" }}>{renderItem(item)}</li>)}
          </ul>
        </section>
      ))}
    </div>
  );
}
