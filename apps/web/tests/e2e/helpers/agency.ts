import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { activateWithToken } from "./welcome";

// Shared by agn-002 and agn-003: sign-in, admin activation of a staff login (the staff-create response never carries the link
// token -- S3 -- so the spec activates it the way an admin re-sends it), and a freshly registered + approved agency.

export async function signIn(page: Page, email: string, password: string, landing = "/overseas/agent/dashboard") {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

export async function adminActivate(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=agent&provisioning_status=pending_setup")).json();
  const staff = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${staff.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

export async function registerApprovedAgency(page: Page, unique: number, label = "agn002") {
  const email = `${label}-m-${unique}@example.local`;
  const agency = `Sigma Overseas ${label} ${unique}`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Sigma Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await fillAgentKyc(page);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/registration-status");
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await verifyAllKyc(page.request, agency);
  await page.goto("/overseas/admin/agents");
  await page.locator(".card", { hasText: agency }).getByRole("button", { name: "Approve" }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();
  return email;
}

// AGN-024 (DEC-SCOPE-224): an agent signup carries PAN, Aadhaar and licence; approval needs all three verified.
export const KYC_PDF = { name: "kyc.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };
export const KYC_NUMBERS = { pan_number: "ABCDE1234F", aadhaar_last4: "1234", license_number: "LIC-2026/001" };

export async function fillAgentKyc(page: Page) {
  for (const [name, value] of Object.entries(KYC_NUMBERS)) await page.fill(`input[name="${name}"]`, value);
  for (const name of ["pan_file", "aadhaar_file", "license_file"]) await page.setInputFiles(`input[name="${name}"]`, KYC_PDF);
}

export function kycMultipart(fields: Record<string, string>) {
  return { ...fields, ...KYC_NUMBERS, pan_file: KYC_PDF, aadhaar_file: KYC_PDF, license_file: KYC_PDF };
}

export async function verifyAllKyc(request: APIRequestContext, agency: string) {
  const list = await (await request.get(`/api/v1/overseas-admin/agent-orgs?status=pending&q=${encodeURIComponent(agency)}`)).json();
  const org = list.items.find((o: { name: string }) => o.name === agency);
  expect(org, `pending org ${agency}`).toBeTruthy();
  const docs = await (await request.get(`/api/v1/overseas-admin/agent-orgs/${org.id}/kyc-documents`)).json();
  for (const doc of docs.items) expect((await request.post(`/api/v1/overseas-admin/agent-orgs/${org.id}/kyc-documents/${doc.id}/verify`)).ok()).toBeTruthy();
}
