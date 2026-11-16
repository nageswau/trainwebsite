"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { detailMessage } from "@/lib/apiErrors";
import { DIVISION_LABEL, heldStudentDivisions, studentHome, type RoleAssignment, type StudentDivision } from "@/lib/dualEnrolment";
import { clearPermissions } from "@/lib/usePermissions";

// ENH-033 (DEC-SCOPE-441 D3): a student enrolled in both IT and Overseas moves between the two student portals without signing in
// again. Shown only on a student portal and only when both student assignments are active; the server re-checks the switch.
export default function PortalSwitcher({ pathname }: { pathname: string }) {
  const router = useRouter();
  const current: StudentDivision | null = pathname.startsWith("/it/student") ? "it" : pathname.startsWith("/overseas/student") ? "overseas" : null;
  const [held, setHeld] = useState<StudentDivision[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    fetch("/api/v1/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((user: { role_assignments?: RoleAssignment[] } | null) => !cancelled && setHeld(heldStudentDivisions(user?.role_assignments)))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [current]);

  if (!current || held.length < 2) return null;

  async function choose(division: StudentDivision) {
    if (division === current || busy) return;
    setBusy(true);
    setError(null);
    const response = await fetch("/api/v1/auth/switch-portal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ division }) }).catch(() => null);
    if (!response?.ok) {
      setBusy(false);
      setError(response ? detailMessage((await response.json().catch(() => null))?.detail, "Could not switch portal.") : "Could not switch portal.");
      return;
    }
    clearPermissions(); // the other portal has its own sidebar permissions
    router.push(studentHome(division));
    router.refresh();
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <label className="muted" htmlFor="portal-switcher" style={{ whiteSpace: "nowrap" }}>Portal</label>
      <select id="portal-switcher" className="input" value={current} disabled={busy} onChange={(e) => choose(e.target.value as StudentDivision)} style={{ width: "auto" }}>
        {held.map((d) => <option key={d} value={d}>{DIVISION_LABEL[d]} Student</option>)}
      </select>
      {error && <span role="alert" className="error">{error}</span>}
    </div>
  );
}
