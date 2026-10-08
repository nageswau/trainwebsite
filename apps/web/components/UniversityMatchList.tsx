import Link from "next/link";
import type { ReactNode } from "react";

import { plural } from "@/lib/plural";
import type { ManagerRef } from "@/lib/telecaller";
import { label, RELATIONSHIPS, type UniversityMatch, universityPath, visibilityLabel } from "@/lib/universities";

// upc-004 UD5: the "already exists" panel (EVID-020 §26) -- existing relationship, assigned manager, current stage, last contact and next
// follow-up. Stage, last contact and next follow-up show "—" until upc-007 / upc-006 / upc-020 record them. `linkable` opens the master
// record (partnership roles only; BDMs cannot); `action` adds a per-match button (the BDM form's "Link and save").
function managerText(m: UniversityMatch): string {
  const name = (ref: ManagerRef, slot: string) => `${ref.full_name} (${slot}${ref.active ? "" : ", inactive"})`;
  const owners = [m.primary_manager && name(m.primary_manager, "primary"), m.backup_manager && name(m.backup_manager, "backup")].filter(Boolean);
  return owners.length ? owners.join(", ") : "Unassigned";
}

export default function UniversityMatchList({ matches, total, linkable = false, action }: {
  matches: UniversityMatch[]; total: number; linkable?: boolean; action?: (m: UniversityMatch) => ReactNode;
}) {
  return (
    <>
      <ul className="list-clean" style={{ display: "grid", gap: 8, margin: "8px 0" }}>
        {matches.map((m) => {
          const title = `${m.university_code} · ${m.name}`;
          return (
            <li key={m.id} style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "8px 12px", background: "#fff", color: "var(--ink)" }}>
              <strong>{linkable ? <Link href={universityPath(m.id)} style={{ color: "var(--blue)", textDecoration: "underline" }}>{title}</Link> : title}</strong>
              <div className="muted">{[m.country.name, m.city, visibilityLabel(m)].filter(Boolean).join(" · ")}</div>
              <dl style={{ display: "grid", gridTemplateColumns: "minmax(110px, max-content) 1fr", gap: "2px 12px", margin: "6px 0 0", fontSize: 14 }}>
                {[
                  ["Existing relationship", label(RELATIONSHIPS, m.existing_relationship)],
                  ["Assigned manager", managerText(m)],
                  ["Current stage", "—"],
                  ["Last contact", "—"],
                  ["Next follow-up", "—"],
                ].map(([term, value]) => [
                  <dt key={`${term}-t`} className="muted">{term}</dt>,
                  <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>,
                ])}
              </dl>
              {action && <div style={{ marginTop: 8 }}>{action(m)}</div>}
            </li>
          );
        })}
      </ul>
      {total > matches.length && <p style={{ margin: 0 }}>{plural(total - matches.length, "more matching university", "more matching universities")}.</p>}
    </>
  );
}
