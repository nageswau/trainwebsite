import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { counselorUniversityPath, VIEW_REFUSED } from "@/lib/universityView";

// upc-030 (DEC-SCOPE-161 §5): the counselor's way in to the University 360 view -- the published, active universities (the public
// catalogue list is exactly the counselor's UV3 scope). A GET form, so search works without JavaScript and the query is in the URL.
type CatalogueUniversity = { id: string; name: string; city: string };
const SHOWN = 50;

export default async function CounselorUniversitiesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const q = ((await searchParams).q ?? "").trim().slice(0, 100);
  let user: User, items: CatalogueUniversity[];
  try {
    [user, items] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<CatalogueUniversity[]>(`/api/v1/public/universities${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (user.role !== "counselor" || user.division !== "overseas") return accessDenied(user, VIEW_REFUSED);
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Universities</div>
            <h2>Partner universities</h2>
            <p className="muted">What each university offers: courses, entry and English requirements, contacts and documents.</p>
          </div>
        </div>
        <form method="get" role="search" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end", marginBottom: 16 }}>
          <label style={{ flex: "1 1 240px" }}>
            Search by name or city
            <input name="q" type="search" defaultValue={q} maxLength={100} />
          </label>
          <button className="btn" type="submit">Search</button>
        </form>
        {items.length === 0 ? (
          <p className="muted" role="status">{q ? `No universities match “${q}”.` : "No universities are published yet."}</p>
        ) : (
          <>
            <ul className="action-grid" style={{ listStyle: "none", padding: 0 }}>
              {items.slice(0, SHOWN).map((u) => (
                <li key={u.id} className="action-card">
                  <h3 style={{ margin: 0 }}><Link href={counselorUniversityPath(u.id)}>{u.name}</Link></h3>
                  <p className="muted" style={{ margin: 0 }}>{u.city}</p>
                </li>
              ))}
            </ul>
            {items.length > SHOWN && <p className="muted">Showing {SHOWN} of {items.length}. Search to narrow the list.</p>}
          </>
        )}
      </div>
    </PortalShell>
  );
}
