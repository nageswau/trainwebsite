import { test, expect, type Page } from "@playwright/test";

// nehn-023 -- the student requests a correction from their session row (no UUID anywhere), the trainer is notified and
// approves it from the pending queue with a comment, and the student is notified of the outcome.
// Requires the stack running via `docker compose up` with `python -m app.seed` already applied.
async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const titles = async (page: Page) => ((await (await page.request.get("/api/v1/workflows/notifications")).json()) as { title: string; body: string }[]);

test("student requests a correction from a row; trainer approves it from the queue (nehn-023 AC1-AC3)", async ({ browser }) => {
  const studentPage = await (await browser.newContext()).newPage();
  await signIn(studentPage, "student.it@edusphere.local", "/it/student/dashboard");
  await studentPage.goto("/it/student/attendance");

  const panel = studentPage.locator(".action-card", { has: studentPage.getByRole("heading", { name: "Request correction" }) });
  const button = panel.getByRole("button", { name: /^Request correction for / }).first();
  const name = (await button.getAttribute("aria-label"))!;
  const [, date, batch] = name.match(/^Request correction for (.+), (.+)$/)!;
  await button.click();
  await panel.getByLabel("Correct status").selectOption({ index: 0 });
  await panel.getByLabel("Reason").fill(`nehn-023 e2e: I attended the ${date} session.`);
  await panel.getByRole("button", { name: "Submit request" }).click();
  await expect(panel.locator(".form-message")).toHaveText("Correction request submitted.");
  await expect(panel.locator("tr", { hasText: date }).filter({ hasText: batch }).getByText("Correction pending")).toBeVisible();
  // AC1: no record UUID anywhere on the page
  await expect(studentPage.locator("main")).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/);

  const trainerPage = await (await browser.newContext()).newPage();
  await signIn(trainerPage, "trainer@edusphere.local", "/it/trainer/dashboard");
  // AC2: the trainer has an in-app notification for the new request
  expect((await titles(trainerPage)).some(n => n.title === "Attendance correction requested" && n.body.includes(date))).toBe(true);
  await trainerPage.goto("/it/trainer/attendance");
  const queue = trainerPage.locator(".action-card", { has: trainerPage.getByRole("heading", { name: "Pending corrections" }) });
  const item = queue.locator("li", { hasText: `nehn-023 e2e: I attended the ${date} session.` }).first();
  await item.getByLabel("Comment (optional)").fill("Checked the register.");
  await item.getByRole("button", { name: /^Approve correction for / }).click();
  await expect(trainerPage.locator(".form-message")).toHaveText("Correction approved.");
  await expect(queue.locator("li", { hasText: `nehn-023 e2e: I attended the ${date} session.` })).toHaveCount(0);

  // AC3: the student is told the outcome, and the row can be corrected again
  expect((await titles(studentPage)).some(n => n.title === "Attendance correction approved" && n.body.includes("Checked the register."))).toBe(true);
  await studentPage.reload();
  await expect(panel.getByRole("button", { name: `Request correction for ${date}, ${batch}` })).toBeVisible();
});
