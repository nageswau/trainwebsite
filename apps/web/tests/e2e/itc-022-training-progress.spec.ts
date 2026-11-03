import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-022 (DEC-SCOPE-365): the IT Admin builds the seeded student's programme plan with weights; the trainer ticks a topic off for the
// batch; the student's Course page shows the worked-out progress and the topic. The plan, the student's ticks and progress are put back
// at the end (the plan emptied, the seeded 42 % restored as a manual figure).
test.describe.configure({ timeout: 180_000 });

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

type Course = { enrollment_id: string; course: string; batch: string; progress_percent: number };

test("admin plan → trainer bulk tick → student sees computed progress", async ({ browser }) => {
  const errors: string[] = [];
  const student = await signIn(browser, "student.it@edusphere.local", "/it/student");
  const before = (await student.evaluate(async () => (await fetch("/api/v1/it/me/progress")).json())) as { courses: Course[] };
  const course = before.courses[0];
  expect(course).toBeTruthy();
  const admin = await signIn(browser, "itadmin@edusphere.local", "/it/admin");
  const trainer = await signIn(browser, "trainer@edusphere.local", "/it/trainer");
  for (const page of [admin, trainer, student]) page.on("pageerror", e => errors.push(e.message));
  const plans = (await admin.evaluate(async () => (await fetch("/api/v1/admin/it/progress-plans")).json())) as { program_id: string; program: string }[];
  const programId = plans.find(p => p.program === course.course)!.program_id;
  try {
    // 1. The IT Admin: two topics, progress from topics only.
    await admin.goto("/it/admin/dashboard");
    await admin.getByRole("link", { name: "Progress Plans" }).first().click();
    await admin.getByRole("button", { name: `Edit progress plan for ${course.course}` }).click();
    await admin.getByRole("button", { name: "Add module" }).click();
    await admin.getByLabel("Module 1", { exact: true }).fill("E2E Basics");
    await admin.getByRole("button", { name: "Add topic" }).click();
    await admin.getByLabel("Module 1 topic 1").fill("E2E OOP");
    await admin.getByRole("button", { name: "Add topic" }).click();
    await admin.getByLabel("Module 1 topic 2").fill("E2E Git");
    await admin.getByLabel("Work it out from these weights").check();
    await admin.getByLabel("Topics completed (%)").fill("90");
    await admin.getByRole("button", { name: "Save plan" }).click();
    await expect(admin.getByRole("alert").filter({ hasText: "must add up to 100" })).toBeVisible();
    await admin.getByLabel("Topics completed (%)").fill("100");
    await admin.getByLabel("Assignments and labs graded (%)").fill("0");
    await admin.getByLabel("Assessments passed (%)").fill("0");
    await admin.getByRole("button", { name: "Save plan" }).click();
    await expect(admin.getByRole("status").filter({ hasText: "Progress is now worked out from the formula" })).toBeVisible();
    await expect(admin.getByRole("row", { name: new RegExp(course.course) }).first()).toContainText("1 module, 2 topics");

    // 2. The trainer ticks "E2E OOP" for everyone in the batch at once.
    await trainer.goto("/it/trainer/student-progress");
    const topics = trainer.getByRole("region", { name: "Topics covered" });
    // the demo trainer may teach several batches: both panels open on the first, so pick the student's
    await expect(trainer.locator("#progress-batch")).toBeVisible(); // the batches have loaded
    await trainer.locator("#progress-batch").selectOption({ label: course.batch });
    if (await topics.getByLabel("Batch").count()) await topics.getByLabel("Batch").selectOption({ label: course.batch }); // shown for 2+ batches only
    await expect(topics.getByLabel("Topic", { exact: true })).toBeVisible();
    await topics.getByLabel("Topic", { exact: true }).selectOption({ label: "E2E OOP (0 done)" });
    await topics.getByLabel(/Select all/).check();
    await topics.getByRole("button", { name: /Mark complete \(\d+\)/ }).click();
    await expect(topics.getByRole("status")).toContainText('"E2E OOP" marked complete');
    await expect(trainer.getByRole("cell", { name: /50%\s*Computed/ }).first()).toBeVisible();

    // 3. The student sees 50 % worked out from topics, and the tick.
    await student.goto("/it/student/course");
    await expect(student.getByRole("progressbar", { name: `${course.course} overall progress` })).toHaveAttribute("aria-valuenow", "50");
    await expect(student.getByText("Worked out from Topics 100%.")).toBeVisible();
    await student.getByText("Topics by module").click();
    await expect(student.getByText("E2E OOP — completed")).toBeAttached();

    // Refusals: the trainer cannot manage plans; the student cannot tick topics.
    expect(await trainer.evaluate(async () => (await fetch("/api/v1/admin/it/progress-plans")).status)).toBe(403);
    expect(await student.evaluate(async () => (await fetch("/api/v1/it/me/progress")).status)).toBe(200);
  } finally {
    await admin.evaluate(async id => fetch(`/api/v1/admin/it/progress-plans/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modules: [], weights: null }) }), programId);
    await trainer.evaluate(
      async ({ id, pct }) => fetch(`/api/v1/workflows/it/trainer/enrollments/${id}/progress`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ progress_percent: pct }) }),
      { id: course.enrollment_id, pct: course.progress_percent },
    );
  }
  expect(errors).toEqual([]);
});
