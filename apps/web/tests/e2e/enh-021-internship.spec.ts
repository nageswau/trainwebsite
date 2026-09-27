import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-021 (docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md, AC21-1, AC21-3, AC21-5,
// AC21-8): a Platinum school's coordinator adds an internship through the real form, marks it completed and uploads a
// certificate; the parent downloads it; the dashboard KPI counts the student. Setup is API-only on a throwaway school.
const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh021-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const ctx = { studentId: "", parentEmail: email("parent") };
const PDF = Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n");

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-021 internship", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 021 School ${unique}`, coordinator_full_name: "E2E 021 Coordinator", coordinator_email: email("coord") });
    const tier = await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } });
    expect(tier.ok()).toBeTruthy();
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: `Ravi 021 ${unique}`, grade_or_class: "Grade 11", parent_name: "E2E 021 Parent", parent_email: ctx.parentEmail } });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    const accept = await playwrightRequest.newContext({ baseURL });
    const accepted = await accept.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: INVITE_PASSWORD } });
    expect(accepted.ok()).toBeTruthy();
    await accept.dispose();
  });

  test("coordinator adds, completes and certifies an internship", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.goto(`/school/coordinator/students/${ctx.studentId}`);
    await page.getByRole("button", { name: "Add internship" }).click();
    await page.getByLabel("Role").fill("Design intern");
    await page.getByLabel("Company").fill("Acme Studio");
    await page.getByLabel("Start date (optional)").fill("2026-05-01");
    await page.getByLabel("End date (optional)").fill("2026-06-30");
    await page.getByLabel("Completion", { exact: true }).selectOption("completed");  // not the "Portfolio completion" meter
    await page.getByLabel("Attendance % (optional)").fill("92");
    await page.getByLabel("Skills acquired (optional)").fill("Figma, Research");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    const details = page.locator(".internship-details");
    await expect(details.getByText("Completed", { exact: true })).toBeVisible();
    await expect(details.getByText("92%")).toBeVisible();
    await page.getByLabel(/Upload certificate/).setInputFiles({ name: "cert.pdf", mimeType: "application/pdf", buffer: PDF });
    await expect(details.getByRole("status")).toHaveText("Certificate saved.");
    await expect(details.getByRole("link", { name: "Download certificate (PDF)" })).toBeVisible();
  });

  test("parent downloads the certificate", async ({ page }) => {
    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Download certificate (PDF)" }).click()]);
    expect(download.suggestedFilename()).toBe("internship-certificate.pdf");
  });

  test("dashboard KPI counts the student", async () => {
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const data = await (await coord.get("/api/v1/school/dashboard")).json();
    const kpi = data.school_crm_kpis.find((k: { key: string }) => k.key === "internships");
    expect(kpi).toMatchObject({ tracked: true, value: 1 });
    await coord.dispose();
  });

  for (const width of [320, 768]) {
    test(`student page has no page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
      await page.goto(`/school/coordinator/students/${ctx.studentId}`);
      await expect(page.locator(".internship-details")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
  }
});
