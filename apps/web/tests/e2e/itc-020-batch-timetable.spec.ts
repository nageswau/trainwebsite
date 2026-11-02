import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-020 (DEC-SCOPE-344): the IT Admin adds a weekly slot to the seeded PY-FS-AUG-2026 batch (today's weekday, so it is in this week's
// calendar), the enrolled student sees the class, the admin cancels it with a reason, and then the student no longer sees it while the
// batch's trainer sees it as cancelled. The slot is removed again at the end, so reruns on one database do not hit the overlap rule.
test.describe.configure({ timeout: 120_000 });

const BATCH = "PY-FS-AUG-2026";
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

function todayWeekday(): number {
  const day = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", weekday: "long" }).format(new Date());
  return DAYS.indexOf(day);
}

test("an admin schedules and cancels a class; the student and trainer calendars follow", async ({ browser }) => {
  const stamp = Date.now();
  const topic = `itc-020 e2e ${stamp}`;
  const consoleErrors: string[] = [];
  const admin = await signIn(browser, "itadmin@edusphere.local", "/it/admin");
  admin.on("pageerror", (e) => consoleErrors.push(e.message));
  const batches = (await (await admin.request.get("/api/v1/admin/batches")).json()) as { id: string; name: string }[];
  const batch = batches.find((b) => b.name === BATCH)!;
  expect(batch).toBeTruthy();
  for (const old of (await (await admin.request.get(`/api/v1/it/batches/${batch.id}/timetable`)).json()).items as { id: string; topic: string | null }[]) {
    if (old.topic?.startsWith("itc-020 e2e")) await admin.request.delete(`/api/v1/it/batches/${batch.id}/timetable/${old.id}`);
  }

  await admin.goto("/it/admin/timetable");
  await expect(admin.getByRole("heading", { name: "Timetable", level: 2 })).toBeVisible();
  await admin.getByLabel("Batch", { exact: true }).selectOption(batch.id);
  await admin.getByLabel("Day", { exact: true }).selectOption(String(todayWeekday()));
  await admin.getByLabel("Starts (IST)").fill("05:10");
  await admin.getByLabel("Ends (IST)").fill("05:50");
  await admin.getByLabel("Class link (optional)").fill("https://meet.example/itc020");
  await admin.getByLabel("Topic (optional)").fill(topic);
  await admin.getByRole("button", { name: "Add slot" }).click();
  await expect(admin.getByRole("status")).toHaveText("Slot added.");
  await expect(admin.getByText(topic, { exact: true })).toBeVisible();

  const student = await signIn(browser, "student.it@edusphere.local", "/it/student");
  await student.goto("/it/student/timetable");
  await expect(student.getByText(topic, { exact: true })).toBeVisible();
  await expect(student.getByRole("button", { name: /Cancel/ })).toHaveCount(0);

  await admin.getByRole("button", { name: new RegExp(`Cancel ${topic}`) }).click();
  await admin.getByLabel(/Reason for cancelling/).fill("Trainer unwell");
  await admin.getByRole("button", { name: "Confirm cancellation" }).click();
  await expect(admin.getByText("Cancelled: Trainer unwell")).toBeVisible();

  await student.reload();
  await expect(student.getByRole("heading", { name: /Week of/ })).toBeVisible();
  await expect(student.getByText(topic, { exact: true })).toHaveCount(0);

  const trainer = await signIn(browser, "trainer@edusphere.local", "/it/trainer");
  await trainer.goto("/it/trainer/timetable");
  const row = trainer.getByRole("listitem").filter({ hasText: topic });
  await expect(row).toContainText("Cancelled: Trainer unwell");

  const slots = (await (await admin.request.get(`/api/v1/it/batches/${batch.id}/timetable`)).json()).items as { id: string; topic: string | null }[];
  for (const s of slots.filter((s) => s.topic === topic)) expect((await admin.request.delete(`/api/v1/it/batches/${batch.id}/timetable/${s.id}`)).status()).toBe(204);
  expect(consoleErrors).toEqual([]);
});

test("the calendar fits a phone without sideways scrolling", async ({ browser }) => {
  const page = await signIn(browser, "student.it@edusphere.local", "/it/student");
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/it/student/timetable");
  await expect(page.getByRole("heading", { name: /Week of/ })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
