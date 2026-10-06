import Link from "next/link";

import { safeNextPath } from "@/lib/safeNext";

// tel-001 (TL1, AC5): a signed-out telecaller picks their team's portal (IT telecallers belong to the IT division, Overseas to Overseas);
// managers sign in at Administration. `next` passes through only when it is a same-origin path.
export default async function TelecallerSignInPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const next = safeNextPath((await searchParams).next ?? null);
  const suffix = next ? `?next=${encodeURIComponent(next)}` : "";
  // A manager lands only on manager pages; any other telecaller page would refuse them, so Administration keeps `next` only for those.
  const adminSuffix = next && next.startsWith("/telecaller/manager") ? suffix : "";
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/" className="muted">← Corporate website</Link>
        <h1 style={{ marginTop: 22, fontSize: 28 }}>Telecaller sign-in</h1>
        <p className="muted">Choose your team&apos;s portal. Telecaller Managers sign in at <Link href={`/admin/login${adminSuffix}`}>Administration</Link>.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/it/login${suffix}`}>IT team</Link>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/overseas/login${suffix}`}>Overseas team</Link>
        </div>
      </div>
    </div>
  );
}
