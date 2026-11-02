import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-021 (DEC-SCOPE-349): the trainer marks the seeded student on approved leave, the student and trainer see "Approved leave", and
// the IT Admin's leave policy moves the student's attendance % exactly as its rule says. The policy is put back to "attended" at the end.
test.describe.configure({ timeout: 120_000 });

const BATCH = "PY-FS-AUG-2026";
const RULES = "/api/v1/workflows/it/certificates/rules";

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

test("approved leave is marked, labelled, and counted by the admin's policy", async ({ browser }) => {
  const errors: string[] = [];
  const day = new Date(Date.UTC(2025, 0, 1) + (Date.now() % 300) * 86_400_000).toISOString().slice(0, 10);
  const admin = await signIn(browser, "itadmin@edusphere.local", "/it/admin");
  const trainer = await signIn(browser, "trainer@edusphere.local", "/it/trainer");
  const student = await signIn(browser, "student.it@edusphere.local", "/it/student");
  for (const page of [admin, trainer, student]) page.on("pageerror", (e) => errors.push(e.message));

  try {
    await trainer.goto("/it/trainer/attendance");
    const form = trainer.getByRole("form", { name: "Mark attendance" });
    const batch = form.getByLabel("Batch");
    await expect(batch.locator("option", { hasText: BATCH })).toHaveCount(1);
    await batch.selectOption({ label: (await batch.locator("option", { hasText: BATCH }).textContent())! });
    await form.getByLabel("Session date").fill(day);
    await form.getByLabel("Arjun Rao status").selectOption({ label: "Approved leave" });
    await form.getByRole("button", { name: "Save attendance" }).click();
    await expect(trainer.getByText("Attendance saved.")).toBeVisible();

    // QA21-01: the trainer's own attendance table names the leave too (found with the table's search; the row is on a later page).
    await trainer.reload();
    await trainer.getByLabel("Search records").fill("approved leave");
    await expect(trainer.locator("tbody tr", { hasText: "approved leave" }).first()).toBeVisible();
    await expect(trainer.locator("main")).not.toContainText(/excused/i);

    await student.goto("/it/student/attendance");
    await expect(student.locator("main")).toContainText("Approved leave");
    await expect(student.locator("main")).not.toContainText(/excused/i);

    const rows = (await (await student.request.get("/api/v1/workflows/it/student/attendance")).json()) as { status: string }[];
    const n = (status: string) => rows.filter((r) => r.status === status).length;
    const [kept, absent, leave] = [n("present") + n("late"), n("absent"), n("excused")];
    expect(leave).toBeGreaterThan(0);
    const expected = {
      attended: Math.round(((kept + leave) * 100) / (kept + absent + leave)),
      excluded: Math.round((kept * 100) / (kept + absent)),
      absent: Math.round((kept * 100) / (kept + absent + leave)),
    };

    await admin.goto("/it/admin/certificates");
    for (const [policy, label] of [["absent", "Absent"], ["excluded", "Left out of the percentage"], ["attended", "Attended"]] as const) {
      await admin.getByLabel("Approved leave counts as").selectOption({ label });
      await admin.getByRole("button", { name: "Save rules" }).click();
      await expect(admin.getByText("Certificate rules saved. They apply to the next eligibility check.")).toBeVisible();
      const body = await (await student.request.get("/api/v1/portal/it/student/attendance")).json();
      expect(body.metrics.find((m: { label: string }) => m.label === "Attendance").value).toBe(`${expected[policy]}%`);
    }
    await admin.reload();
    await expect(admin.getByLabel("Approved leave counts as")).toHaveValue("attended");

    expect((await trainer.request.put(RULES, { data: { min_progress_percent: 100, min_attendance_percent: 75, leave_policy: "absent" } })).status()).toBe(403);
    expect(errors).toEqual([]);
  } finally {
    const current = await (await admin.request.get(RULES)).json();
    await admin.request.put(RULES, { data: { ...current, leave_policy: "attended" } });
  }
});
