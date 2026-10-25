import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { signIn } from "./agency";
import { E2E_PASSWORD, activateWithToken, createAndActivate } from "./welcome";

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

// A counselor's walk-in student never sees their link token (S3), so a spec activates the login the way the admin's Re-send does (its
// response carries the token in dev/test), as csc-002 does. `request` is a separate context: the page keeps its own session.
export async function activateWalkInStudent(request: APIRequestContext, email: string): Promise<void> {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=overseas_student&provisioning_status=pending_setup")).json();
  const student = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${student.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

// ccrm-040 (DEC-SCOPE-275 CN7): WhatsApp to a student needs the student's own ENH-014 opt-in, which only the student can give.
export async function studentOptsInToWhatsApp(request: APIRequestContext, email: string): Promise<void> {
  await activateWalkInStudent(request, email);
  expect((await request.post("/api/v1/auth/login", { data: { email, password: E2E_PASSWORD, division: "overseas" } })).ok()).toBeTruthy();
  expect((await request.put("/api/v1/account/notification-preferences", { data: { whatsapp: true, sms: false } })).ok()).toBeTruthy();
  await request.post("/api/v1/auth/logout");
}
