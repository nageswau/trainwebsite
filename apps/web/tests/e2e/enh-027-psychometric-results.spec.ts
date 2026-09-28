import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-027 -- structured psychometric results (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md, AC07).
// API-only setup on a throwaway school (like enh-013/enh-026): a psychometric-team member, one student with a linked parent and one
// assigned assessment. The school gets a tier first -- psychometric tests are a tiered service (ENH-022), and a tierless school's
// record would be refused. The feature is driven through the real UI: keyboard-only entry, the 360° tab, the parent's page, 320 px.
const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh027-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const ctx = { studentName: `Asha 027 ${unique}`, parentEmail: email("parent"), studentId: "" };
const recordButton = (verb: "Record" | "Edit") => `${verb} results for ${ctx.studentName} — Aptitude Test`;

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

test.describe.serial("ENH-027 psychometric results", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 027 School ${unique}`, coordinator_full_name: "E2E 027 Coordinator", coordinator_email: email("coord") });
    const tier = await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } });
    expect(tier.ok()).toBeTruthy();
    await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role: "psychometric_team", full_name: "E2E 027 Psych", email: email("psych"), school_ids: [school.id] });
    await admin.dispose();

    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: ctx.studentName, grade_or_class: "Grade 9", parent_name: "E2E 027 Parent", parent_email: ctx.parentEmail } });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    const accept = await playwrightRequest.newContext({ baseURL });
    const accepted = await accept.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: INVITE_PASSWORD } });
    expect(accepted.ok()).toBeTruthy();
    await accept.dispose();

    const psych = await apiAs(email("psych"), E2E_PASSWORD);
    const assigned = await psych.post("/api/v1/school/psychometric-team/records", { data: { school_student_id: ctx.studentId, assessment_type: "Aptitude Test" } });
    expect(assigned.status()).toBe(201);
    await psych.dispose();
  });

  test("the team records results with the keyboard only", async ({ page }) => {
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.getByRole("button", { name: recordButton("Record") }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: `Results — ${ctx.studentName} · Aptitude Test` })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator("#psy-result-test-date")).toBeFocused();
    await page.locator("#psy-result-test-date").fill("2026-09-10");
    await page.locator("#psy-result-strengths").fill("Logical reasoning, Verbal ability");
    await page.locator("#psy-result-recommended-stream").fill("Science (PCM)");
    await page.locator("#psy-result-counsellor-remarks").fill("Strong analytical profile.");
    await page.locator("#psy-result-follow-up-on").fill("2026-10-15");
    await page.getByRole("button", { name: "Save results" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Results saved.")).toBeVisible();
    await expect(page.getByRole("button", { name: recordButton("Edit") })).toBeVisible();
  });

  test("the 360° Psychometric tab shows the structured results", async ({ page }) => {
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.goto(`/school/psychometric-team/students/${ctx.studentId}/360?tab=psychometric_assessment`);
    const panel = page.getByRole("tabpanel");
    await panel.getByText("Aptitude Test — results").click();
    await expect(panel).toContainText("Logical reasoning, Verbal ability");
    await expect(panel).toContainText("Science (PCM)");
    await expect(panel).toContainText("Strong analytical profile.");
  });

  test("the parent sees them on the child page", async ({ page }) => {
    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    await page.getByText("Aptitude Test — results").click();
    await expect(page.getByText("Logical reasoning, Verbal ability")).toBeVisible();
  });

  test("the editor fits a 320 px phone without page overflow", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.getByRole("button", { name: recordButton("Edit") }).click();
    await expect(page.locator("#psy-result-strengths")).toBeVisible();
    const widths = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: window.innerWidth }));
    expect(widths.doc).toBeLessThanOrEqual(widths.view);
  });
});
