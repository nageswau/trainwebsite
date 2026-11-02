import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-023 (DEC-SCOPE-352): the IT Admin sets a programme's at-risk thresholds on the At Risk page; the student record shows the at-risk
// card; other roles cannot change thresholds and the student cannot read flags. The daily sweep itself is covered by the API tests.
// The seeded programme's thresholds are put back (all off) at the end.
test.describe.configure({ timeout: 120_000 });

const PROGRAM = "Python Full Stack";

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

test("the IT Admin sets thresholds per programme and other roles are refused", async ({ browser }) => {
  const errors: string[] = [];
  const admin = await signIn(browser, "itadmin@edusphere.local", "/it/admin");
  admin.on("pageerror", (e) => errors.push(e.message));
  try {
    await admin.goto("/it/admin/dashboard");
    await admin.getByRole("link", { name: "At Risk" }).first().click();
    await expect(admin.getByRole("heading", { name: "Students at risk" })).toBeVisible();
    await admin.getByRole("button", { name: `Edit thresholds for ${PROGRAM}` }).click();
    await admin.getByLabel("Minimum attendance %").fill("75");
    await admin.getByLabel("Absences in a row").fill("5");
    await admin.getByRole("button", { name: "Save thresholds" }).click();
    await expect(admin.getByRole("status").filter({ hasText: `Thresholds for ${PROGRAM} saved` })).toBeVisible();
    await admin.reload();
    await expect(admin.getByRole("row", { name: new RegExp(PROGRAM) }).first()).toContainText("Attendance below 75% (after 3 sessions); 5 absences in a row");

    // The student record (360) carries the at-risk card.
    const students = await admin.evaluate(async () => (await fetch("/api/v1/admin/users?role=it_student&division=it")).json());
    const arjun = (students as { id: string; name: string }[]).find((s) => s.name === "Arjun Rao")!;
    await admin.goto(`/it/admin/students/${arjun.id}/profile`);
    await expect(admin.getByRole("heading", { name: /At-risk status/ })).toBeVisible();

    const trainer = await signIn(browser, "trainer@edusphere.local", "/it/trainer");
    expect(await trainer.evaluate(async () => (await fetch("/api/v1/admin/it/risk-thresholds")).status)).toBe(403);
    await trainer.goto("/it/trainer/notifications");
    await expect(trainer.getByRole("heading", { name: "Notifications" })).toBeVisible();
    const student = await signIn(browser, "student.it@edusphere.local", "/it/student");
    expect(await student.evaluate(async () => (await fetch("/api/v1/it/at-risk")).status)).toBe(403);
  } finally {
    const rows = await admin.evaluate(async () => (await fetch("/api/v1/admin/it/risk-thresholds")).json());
    const row = (rows as { program_id: string; program: string }[]).find((r) => r.program === PROGRAM)!;
    await admin.evaluate(async (id) => fetch(`/api/v1/admin/it/risk-thresholds/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ min_sessions: 3 }) }), row.program_id);
  }
  expect(errors).toEqual([]);
});
