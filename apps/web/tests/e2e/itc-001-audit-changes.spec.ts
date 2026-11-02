import { expect, test, type APIRequestContext } from "@playwright/test";

// itc-001 (DEC-SCOPE-335): a trainer re-marks a learner from absent to present with a note; the IT Admin's Audit log shows the row's
// Changes expander with the old and new status and the note as "changed" (never its text), on desktop and phone, opened from the keyboard.

const PASSWORD = "Demo@123";

async function apiLogin(request: APIRequestContext, email: string) {
  expect((await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD, division: "it" } })).ok()).toBeTruthy();
}

/** A random past date, so this run's attendance row is new and its only change row is the one made here. */
const day = () => `2025-${String(1 + Math.floor(Math.random() * 12)).padStart(2, "0")}-${String(1 + Math.floor(Math.random() * 28)).padStart(2, "0")}`;

async function reMark(trainer: APIRequestContext, admin: APIRequestContext): Promise<string> {
  const context = await (await trainer.get("/api/v1/workflows/it/trainer/context")).json();
  const batch = context.batches[0];
  const student = context.students.find((s: { batch_id: string }) => s.batch_id === batch.id);
  const session = day();
  const mark = (status: string, notes: string) =>
    trainer.post("/api/v1/workflows/it/trainer/attendance", { data: { batch_id: batch.id, session_date: session, records: [{ student_id: student.id, status, notes }] } });
  expect((await mark("absent", "")).status()).toBe(201);
  expect((await mark("present", "Arrived after the bus delay")).status()).toBe(201);
  const rows = await (await admin.get("/api/v1/admin/audit?action=attendance.update&limit=50")).json();
  const row = rows.find((r: { metadata: { session_date?: string; student_id?: string } }) => r.metadata.session_date === session && r.metadata.student_id === student.id);
  expect(row.changes).toEqual({ status: ["absent", "present"], notes: "changed" });
  return row.entity_id;
}

for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["phone", { width: 375, height: 812 }]] as const) {
  test(`IT Admin sees an attendance re-mark's old and new values (${label})`, async ({ page, playwright, baseURL }) => {
    await page.setViewportSize(viewport);
    const trainer = await playwright.request.newContext({ baseURL });
    await apiLogin(trainer, "trainer@edusphere.local");
    await apiLogin(page.request, "itadmin@edusphere.local");
    const id = await reMark(trainer, page.request);

    await page.goto(`/it/admin/audit-log?entity_type=attendance&entity_id=${id}`);
    const rows = page.getByRole("table", { name: "Audit log" }).locator("tbody tr");
    await expect(rows).toHaveCount(1);
    const summary = rows.first().locator("summary");
    await expect(summary).toHaveText("2 fields changed");
    await summary.focus();
    await page.keyboard.press("Enter");
    const items = rows.first().getByRole("list", { name: "Changed fields" }).getByRole("listitem");
    await expect(items).toHaveText(["status: absent → present", "notes: changed (value hidden)"]);
    await expect(rows.first()).not.toContainText("bus delay");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await trainer.dispose();
  });
}

test("a trainer still cannot read the audit log", async ({ page }) => {
  await apiLogin(page.request, "trainer@edusphere.local");
  expect((await page.request.get("/api/v1/admin/audit")).status()).toBe(403);
});
