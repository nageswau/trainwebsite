import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// rec-036 (AC1, AC2; CI1-CI7): the seeded IT student holds the certificate of their program and joins the placement pool; the IT admin
// tags that program with a new Skills Master skill on the Programs page, which reaches the student at once as "Course completed" and
// Verified; the recruiter then sees the skill and the candidate's journey (lead → IT student → trained → recruiter candidate → placed).
// Idempotent across runs: the certificate and the opt-in are reused, and every run tags a fresh skill.

const PASSWORD = "Demo@123";
const ADMIN = "itadmin@edusphere.local";
const STUDENT = "student.it@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

async function api(browser: Browser, email: string, division: "it" | "global"): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password: PASSWORD, division } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("course skills reach an opted-in completer when the IT admin tags the program; the recruiter sees them and the journey", async ({ browser, page }) => {
  test.setTimeout(150_000);
  const skillName = `E2E Course Skill ${Date.now()}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  // A fresh Skills Master skill (placement manager).
  const manager = await api(browser, MANAGER, "global");
  const categories = await (await manager.get("/api/v1/recruiter/skill-categories?limit=1")).json();
  const skill = await manager.post("/api/v1/recruiter/skills", { data: { name: skillName, category_id: categories.items[0].id } });
  expect(skill.status(), await skill.text()).toBe(201);

  // The seeded student's enrolment, its program and an issued certificate (reused on later runs).
  const admin = await api(browser, ADMIN, "it");
  const enrolment = ((await (await admin.get("/api/v1/admin/enrollments")).json()) as { id: string; email: string; batch_id: string }[]).find((e) => e.email === STUDENT)!;
  const batch = ((await (await admin.get("/api/v1/admin/batches")).json()) as { id: string; program_id: string; program: string }[]).find((b) => b.id === enrolment.batch_id)!;
  const coordinator = await api(browser, "coordinator@edusphere.local", "it"); // nehn-031: the coordinator issues
  const issued = await coordinator.post(`/api/v1/workflows/it/certificates/${enrolment.id}/issue`, { data: { override: true, override_reason: "rec-036 e2e" } });
  expect([201, 409]).toContain(issued.status()); // 409: issued by an earlier run on this database

  // The student joins the placement pool (a second click adds nothing).
  const student = await api(browser, STUDENT, "it");
  expect((await student.post("/api/v1/account/placement-pool/opt-in", { data: { consent_version: "v1" } })).ok()).toBeTruthy();

  // CI1: the IT admin tags the program on the Programs page.
  await signIn(page, ADMIN, "/it/admin/dashboard");
  await page.goto("/it/admin/programs");
  const slug = ((await (await admin.get("/api/v1/admin/programs")).json()) as { id: string; slug: string }[]).find((p) => p.id === batch.program_id)!.slug;
  await page.getByLabel("Search by title, category, or slug").fill(slug); // the slug is unique; titles repeat in a shared test database
  await page.getByRole("button", { name: `Skills for ${batch.program}` }).click();
  const editor = page.getByRole("region", { name: `Skills taught in ${batch.program}` });
  await expect(editor.getByRole("heading")).toBeFocused();
  const picker = editor.getByRole("combobox", { name: /Add a skill/ });
  await picker.fill(skillName);
  await editor.getByRole("option", { name: new RegExp(skillName) }).click();
  await expect(editor.getByRole("list", { name: "Skills taught" })).toContainText(skillName);
  await editor.getByRole("button", { name: "Save skills" }).click();
  await expect(editor.getByRole("status")).toContainText(/Skills saved\. \d+ candidates? (was|were) updated\./);

  // QA36-03: on a phone the program table scrolls sideways; the editor stays within the visible part, Save included.
  await page.setViewportSize({ width: 375, height: 800 });
  await editor.getByRole("button", { name: "Save skills" }).scrollIntoViewIfNeeded();
  const save = (await editor.getByRole("button", { name: "Save skills" }).boundingBox())!;
  const heading = (await editor.getByRole("heading").boundingBox())!;
  expect(save.x).toBeGreaterThanOrEqual(0);
  expect(heading.x).toBeGreaterThanOrEqual(0);
  expect(heading.x + heading.width).toBeLessThanOrEqual(375);
  await page.setViewportSize({ width: 1280, height: 720 });

  // AC1: the recruiter sees the course skill, Verified; AC2: the journey shows each stage with dates.
  const recruiter = await api(browser, RECRUITER, "it");
  const list = await (await recruiter.get(`/api/v1/recruiter/candidates?q=${encodeURIComponent(STUDENT)}`)).json();
  const candidateId = list.items[0].id as string;
  await page.context().clearCookies();
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/candidates/${candidateId}`);
  const row = page.getByRole("row", { name: new RegExp(skillName) });
  await expect(row).toContainText("Course completed");
  await expect(row).toContainText("Verified");
  const journey = page.getByRole("list", { name: "Candidate journey" });
  await expect(journey.getByRole("listitem", { name: "IT student" })).toContainText(/enrolled \d{1,2} \w{3,4} \d{4}/);
  await expect(journey.getByRole("listitem", { name: "Trained" })).toContainText(batch.program);
  await expect(journey.getByRole("listitem", { name: "Recruiter candidate" })).toContainText("joined the placement pool");

  // 375 px: the journey fits without a horizontal scroll.
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(journey).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
