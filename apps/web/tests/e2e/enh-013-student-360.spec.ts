import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-013 -- Student 360° view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md, AC-01..AC-12).
// Setup is API-only and runs once: a throwaway school (like enh-011/enh-012) with its coordinator, an assigned and an outside
// teacher, a career counselor and a psychometric-team member, one student with data and a linked parent, and one brand-new
// student. The feature itself -- opening the view, switching tabs, setting the career goal -- is driven through the real UI.
// Also guards the browser-QA fixes: no server round trip per tab click (QA-02), no page overflow on a phone (QA-01), and no tab
// hidden under the sticky portal top bar (QA-03).

const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh013-e2e-${who}-${unique}@example.local`;
const ctx: { studentId: string; newStudentId: string; parentEmail: string } = { studentId: "", newStudentId: "", parentEmail: email("parent") };
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";

async function apiAs(emailAddress: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: emailAddress, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${emailAddress}: ${res.status()} ${await res.text()}`);
  return api;
}

async function acceptInvite(token: string) {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post(`/api/v1/school/invites/${token}/accept`, { data: { password: INVITE_PASSWORD } });
  if (!res.ok()) throw new Error(`accept invite: ${res.status()} ${await res.text()}`);
  await api.dispose();
}

async function signIn(page: Page, emailAddress: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", emailAddress);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const tab = (page: Page, name: RegExp) => page.getByRole("tab", { name });

test.describe.serial("ENH-013 Student 360° view", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 360 School ${unique}`, coordinator_full_name: "E2E 360 Coordinator", coordinator_email: email("coord") });
    for (const [role, who] of [["career_counselor", "counselor"], ["psychometric_team", "psych"]]) {
      await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role, full_name: `E2E 360 ${who}`, email: email(who), school_ids: [school.id] });
    }
    await admin.dispose();

    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    for (const who of ["teacher", "outsider"]) {
      const invite = await coord.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: `E2E 360 ${who}`, email: email(who) } });
      await acceptInvite((await invite.json()).development_invite_token);
    }
    const created = await coord.post("/api/v1/school/students", {
      data: { full_name: "Asha 360", grade_or_class: "Grade 7", assigned_teacher_email: email("teacher"), parent_name: "E2E 360 Parent", parent_email: ctx.parentEmail },
    });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    const fresh = await coord.post("/api/v1/school/students", { data: { full_name: "Newly Enrolled 360", grade_or_class: "Grade 6" } });
    ctx.newStudentId = (await fresh.json()).id;
    const entry = await coord.post(`/api/v1/school/students/${ctx.studentId}/portfolio/entries`, { data: { section: "certification", title: "First Aid Certificate", organization: "Red Cross" } });
    expect(entry.status()).toBe(201);
    await coord.dispose();
    await acceptInvite(student.development_invite_token);

    const counselor = await apiAs(email("counselor"), E2E_PASSWORD);
    const record = await counselor.post("/api/v1/school/career-counselor/records", { data: { school_student_id: ctx.studentId, record_type: "guidance_session", notes: "Explored engineering and design pathways." } });
    expect(record.status()).toBe(201);
    await counselor.dispose();
  });

  test("coordinator opens the 360° view from the student page; all 16 tabs; tabs switch without a server round trip (AC-01, QA-02)", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.goto(`/school/coordinator/students/${ctx.studentId}`);
    await page.getByRole("link", { name: "Open 360° view" }).click();
    await page.waitForURL(`**/school/coordinator/students/${ctx.studentId}/360`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Asha 360");
    await expect(page.getByRole("tab")).toHaveCount(16);
    await expect(tab(page, /^Overview/)).toHaveAttribute("aria-selected", "true");

    const pageRequests: string[] = [];
    page.on("request", (r) => { if (r.url().includes("/360")) pageRequests.push(r.url()); });
    await tab(page, /^Certificates/).click();
    await expect(page.getByRole("tabpanel")).toContainText("First Aid Certificate");
    await expect(page).toHaveURL(/\?tab=certificates$/);
    await tab(page, /^Career Guidance/).click();
    await expect(page.getByRole("tabpanel")).toContainText("Explored engineering and design pathways.");
    await tab(page, /^Parent Communication/).click();
    await expect(page.getByRole("tabpanel")).toContainText("not tracked yet (ENH-013b / ENH-014)");
    expect(pageRequests, "switching tabs must not re-request the page").toEqual([]);

    await page.reload();
    await expect(tab(page, /^Parent Communication/)).toHaveAttribute("aria-selected", "true");
  });

  test("an unassigned teacher is refused (AC-02)", async ({ page }) => {
    await signIn(page, email("outsider"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.goto(`/school/teacher/students/${ctx.studentId}/360`);
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByText("This student is not assigned to you")).toBeVisible();
    await expect(page.getByRole("tab")).toHaveCount(0);
  });

  test("a newly enrolled student shows empty states, not errors (AC-04)", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.goto(`/school/coordinator/students/${ctx.newStudentId}/360`);
    await expect(page.getByRole("tab")).toHaveCount(16);
    for (const name of ["Attendance", "Examination Results", "Career Guidance", "Certificates", "Edusphere Programs"]) {
      await tab(page, new RegExp(`^${name}`)).click();
      await expect(page.getByRole("tabpanel").getByRole("status").first()).toContainText(/^(No |Not enrolled)/);
    }
    await expect(page.getByText(/Access unavailable|Something went wrong/)).toHaveCount(0);
  });

  test("the career counselor sets the career goal; the parent sees it read-only (AC-07)", async ({ page }) => {
    await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
    await page.getByRole("link", { name: "Asha 360" }).click();
    await page.waitForURL(`**/school/career-counselor/students/${ctx.studentId}/360`);
    await page.getByRole("button", { name: "Set career goal" }).click();
    const input = page.getByLabel("Career goal", { exact: true });
    await expect(input).toBeFocused();
    await input.fill("Technology");
    await input.press("Enter");
    await expect(page.getByRole("status").filter({ hasText: "Career goal saved." })).toBeVisible();
    await expect(page.locator("h1").locator("xpath=ancestor::div[contains(@class,'card')]")).toContainText("Career goal: Technology");

    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    await page.getByRole("link", { name: "Open 360° view" }).click();
    await page.waitForURL(`**/school/parent/children/${ctx.studentId}/360`);
    await expect(page.getByRole("tabpanel")).toContainText("Technology");
    await expect(page.getByRole("button", { name: /career goal/i })).toHaveCount(0);
  });

  test("the psychometric team sees restricted tabs as unavailable, not empty (AC-05)", async ({ page }) => {
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.goto(`/school/psychometric-team/students/${ctx.studentId}/360`);
    await expect(page.getByRole("tab", { name: /not available for your role/ })).toHaveCount(4);
    await tab(page, /^English Testing/).click();
    await expect(page.getByRole("tabpanel")).toContainText("This section is not available for your role.");
    await expect(page.locator("h1").locator("xpath=ancestor::div[contains(@class,'card')]")).not.toContainText("Grade 7");
  });

  test("keyboard only: arrows, Home/End, Tab into the panel (AC-11)", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.goto(`/school/coordinator/students/${ctx.studentId}/360`);
    await tab(page, /^Overview/).focus();
    await page.keyboard.press("ArrowDown");
    await expect(tab(page, /^Personal Details/)).toBeFocused();
    await expect(tab(page, /^Personal Details/)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(tab(page, /^Edusphere Programs/)).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(tab(page, /^Overview/)).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("tabpanel")).toBeFocused();
  });

  test("phone and scrolled desktop layouts: no page overflow, no tab under the top bar (AC-11, QA-01, QA-03)", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/school/coordinator/students/${ctx.studentId}/360`);
    await expect(page.getByRole("tab")).toHaveCount(16);  // measure the page, not the streamed loading skeleton
    const widths = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: window.innerWidth }));
    expect(widths.doc).toBeLessThanOrEqual(widths.view);
    await tab(page, /^Edusphere Programs/).click();
    await expect(tab(page, /^Edusphere Programs/)).toHaveAttribute("aria-selected", "true");

    await page.setViewportSize({ width: 1366, height: 620 });
    await page.goto(`/school/coordinator/students/${ctx.studentId}/360?tab=career_guidance`);
    await expect(page.getByRole("tab")).toHaveCount(16);
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
    const overviewClickable = await page.evaluate(() => {
      const t = document.querySelector("#s360-tab-overview")!;
      const r = t.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return !!hit && t.contains(hit);
    });
    expect(overviewClickable, "the Overview tab must not sit under the sticky portal top bar").toBe(true);
  });
});
