import Link from "next/link";

import { safeNextPath } from "@/lib/safeNext";

// bdm-001 (B9, AC12): a signed-out BDM picks their portal -- College BDMs belong to the IT division, Agent/School BDMs to Overseas,
// managers to Administration. `next` passes through only when it is a same-origin path.
export default async function BdmSignInPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const next = safeNextPath((await searchParams).next ?? null);
  const suffix = next ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/" className="muted">← Corporate website</Link>
        <h1 style={{ marginTop: 22, fontSize: 28 }}>BDM sign-in</h1>
        <p className="muted">Choose the portal for your module. BDM Managers sign in at <Link href={`/admin/login${suffix}`}>Administration</Link>.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/it/login${suffix}`}>College BDM</Link>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/overseas/login${suffix}`}>Agent / School BDM</Link>
        </div>
      </div>
    </div>
  );
}
