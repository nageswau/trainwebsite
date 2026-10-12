import Link from "next/link";

import type { ManagementPillar } from "@/lib/management";

// mgmt-001 (MG8): one card per pillar the caller's tiers allow. A live entry links to its page; every other entry is plain text marked
// "Coming soon" (the upc-001 PU8 idiom), so nobody follows a link to a page that does not exist yet.
export default function ManagementPillars({ pillars }: { pillars: ManagementPillar[] }) {
  return (
    <div className="grid three">
      {pillars.map((pillar) => {
        const id = `management-pillar-${pillar.title.toLowerCase().replaceAll(" ", "-")}`;
        return (
          <section key={pillar.title} className="card" style={{ padding: 18 }} aria-labelledby={id}>
            <h3 id={id} style={{ fontSize: 18 }}>{pillar.title}</h3>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {pillar.entries.map((entry) => (
                <li key={entry.label} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  {entry.href ? <Link href={entry.href}>{entry.label}</Link> : <><span>{entry.label}</span><span className="badge">Coming soon</span></>}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
