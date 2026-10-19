import { expect, type Page } from "@playwright/test";

import { signIn } from "./agency";
import { E2E_PASSWORD, createAndActivate } from "./welcome";

// csc-002/csc-003: each walk-in spec signs in as its own new overseas counselor. A counselor may send 20 account emails a day
// (DEC-SCOPE-227/228), so specs sharing the seeded demo counselor would exhaust that budget after a few runs.
export async function signInAsFreshCounselor(page: Page, label: string): Promise<string> {
  const email = `${label}-cns-${Date.now()}@example.local`;
  const admin = await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(admin.ok()).toBeTruthy();
  await createAndActivate(page.request, "/api/v1/admin/users", { email, full_name: `${label} Counselor`, role: "counselor", division: "overseas" });
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, email, E2E_PASSWORD, "/overseas/counselor/dashboard");
  return email;
}
