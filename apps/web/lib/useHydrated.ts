"use client";

import { useEffect, useState } from "react";

// bdm-010 (QA10-17): false in the server render and until React owns the page, then true. A server-rendered form disables its
// fields until then, so text typed before hydration can't be wiped by it.
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}
