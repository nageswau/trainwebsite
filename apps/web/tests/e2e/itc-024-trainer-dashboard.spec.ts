import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-024 (DEC-SCOPE-355): the trainer dashboard's four new widgets (today's classes, attendance completion, assessment completion,
// at-risk students) and its batch filter, which lives in the address and refuses a batch that is not the trainer's own. The figures'
// definitions are covered by the API tests; this checks the page wiring, the refusal fallback and the role gate.
test.describe.configure({ timeout: 120_000 });

const TILES = ["Assigned batches", "Today's classes", "Attendance completion", "Assessment completion", "At-risk students"];

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

const tile = (page: Page, label: string) => page.locator(".metric").filter({ has: page.getByText(label, { exact: true }) });

test("the trainer sees the new widgets and narrows them to one batch", async ({ browser }) => {
  const errors: string[] = [];
  const trainer = await signIn(browser, "trainer@edusphere.local", "/it/trainer");
  trainer.on("pageerror", (e) => errors.push(e.message));
  await trainer.goto("/it/trainer/dashboard");
  for (const label of TILES) await expect(tile(trainer, label)).toBeVisible();
  const today = trainer.locator(".panel").filter({ has: trainer.getByRole("heading", { name: "Today's classes" }) });
  await expect(today).toBeVisible();
  const classes = Number(await tile(trainer, "Today's classes").locator("strong").textContent());
  if (classes === 0) await expect(today.getByText("No classes today")).toBeVisible();
  else await expect(today.getByRole("listitem")).toHaveCount(classes);

  const batch = trainer.getByLabel("Batch");
  const options = await batch.locator("option").allTextContents();
  expect(options[0]).toBe("All batches");
  await batch.selectOption({ label: options[1] });
  await trainer.waitForURL(/\?batch=/);
  await expect(tile(trainer, "Assigned batches").locator("strong")).toHaveText("1");
  await trainer.reload();
  await expect(trainer.getByLabel("Batch").locator("option:checked")).toHaveText(options[1]);
  await trainer.getByLabel("Batch").selectOption({ label: "All batches" });
  await trainer.waitForURL((url) => !url.search.includes("batch="));

  // A batch that is not the trainer's falls back to every batch, with the refusal shown.
  await trainer.goto("/it/trainer/dashboard?batch=00000000-0000-4000-8000-000000000000");
  await expect(trainer.locator(".form-error[role=alert]")).toHaveText("Choose one of your batches");
  await expect(tile(trainer, "Assigned batches").locator("strong")).toHaveText(String(options.length - 1));
  expect(errors).toEqual([]);

  const student = await signIn(browser, "student.it@edusphere.local", "/it/student");
  expect(await student.evaluate(async () => (await fetch("/api/v1/portal/it/trainer/dashboard")).status)).toBe(403);
});
