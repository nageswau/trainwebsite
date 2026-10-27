"use client";
import { useEffect, useState } from "react";

// nehn-006 (DEC-SCOPE-295 M9/M10): the signed-in role's permission keys from GET /auth/me/permissions, or null while unknown (loading, or
// the lookup failed). The last answer is kept for the next portal page so a revoked item does not flash back, and every mount asks
// again so a change applies on the next navigation. The API is the authority; this only shapes the menu and the controls.
let cached: string[] | null = null;

export function clearPermissions(): void {
  cached = null;
}

export function usePermissions(enabled = true): string[] | null {
  const [permissions, setPermissions] = useState<string[] | null>(cached);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    (async () => {
      try {
        const response = await fetch("/api/v1/auth/me/permissions", { cache: "no-store" });
        const body = response.ok ? await response.json() : null;
        if (!live || !Array.isArray(body?.permissions)) return;
        cached = body.permissions;
        setPermissions(body.permissions);
      } catch {
        // unknown stays unknown: the nav and controls keep their default
      }
    })();
    return () => {
      live = false;
    };
  }, [enabled]);
  return enabled ? permissions : null;
}
