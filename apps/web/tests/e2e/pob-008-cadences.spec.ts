import { expect, test, type Page } from "@playwright/test";

// pob-008 (DEC-SCOPE-423 B5-B10): the Team Lead adds an outreach cadence on /recruiter/manager/cadences; the recruiter's new company gets a
// first-outreach follow-up, they log LinkedIn outreach to a contact, start the cadence on that message and stop it. The reminder and
// cadence sweeps run in the worker and are asserted in test_pob_008_reminders_cadences.py.

async function signIn(page: Page, email: string, login = "/it/login") {
  await page.context().clearCookies();
  await page.goto(login);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";

test("outreach cadences: the Team Lead's library, a first-outreach follow-up, start and stop on a message", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const failedCalls: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failedCalls.push(r.url()));

  // The Team Lead adds a cadence; the step rules are checked before the round trip.
  await signIn(page, MANAGER, "/admin/login");
  await page.goto("/recruiter/manager/cadences");
  await expect(page.getByRole("heading", { name: "Outreach cadences" })).toBeVisible();
  await page.getByRole("button", { name: "Add cadence" }).click();
  const form = page.getByRole("form", { name: "Add a cadence" });
  const name = `E2E Cadence ${stamp}`;
  await form.getByLabel("Name (required)").fill(name);
  await form.getByLabel("Step 2 day").fill("0");
  await form.getByRole("button", { name: "Add cadence" }).click();
  await expect(form.getByText("Each step must come on a later day than the one before")).toBeVisible();
  await form.getByLabel("Step 2 day").fill("3");
  await form.getByRole("button", { name: "Add step" }).click();
  await form.getByLabel("Step 3 day").fill("7");
  await form.getByRole("button", { name: "Add cadence" }).click();
  await expect(page.getByText("Cadence added.")).toBeVisible();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Day 0 Email → Day 3 LinkedIn → Day 7 Call").first()).toBeVisible();

  // The recruiter: a new company gets its first-outreach follow-up; a contact gets one too.
  await signIn(page, RECRUITER);
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob008 ${stamp} Ltd` } });
  expect(created.status(), await created.text()).toBe(201);
  const companyId = (await created.json()).company.id as string;
  const contactName = `Meera ${stamp}`;
  const added = await page.request.post(`/api/v1/recruiter/companies/${companyId}/contacts`, { data: { name: contactName, mobile: "98450 12345" } });
  expect(added.status(), await added.text()).toBe(201);
  const followUps = (await (await page.request.get(`/api/v1/recruiter/companies/${companyId}/follow-ups`)).json()).items as { reason: string }[];
  expect(followUps.map((f) => f.reason)).toEqual(["first_outreach", "first_outreach"]);

  // LinkedIn outreach to the contact, then the cadence on that message.
  await page.goto(`/recruiter/companies/${companyId}`);
  await page.getByRole("button", { name: "LinkedIn message" }).click();
  await page.getByRole("button", { name: "Log as sent" }).click();
  await expect(page.getByText(`LinkedIn connection request to ${contactName} logged.`)).toBeVisible();
  await page.getByRole("button", { name: `Start cadence for ${contactName}` }).click();
  await page.getByLabel("Cadence", { exact: true }).selectOption({ label: name });
  await expect(page.getByText(/This message is step 1/)).toBeVisible();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByText(`Cadence started for ${contactName}.`)).toBeVisible();
  await expect(page.getByText(new RegExp(`Cadence: ${name} · step 1 of 3 · next`))).toBeVisible();
  await page.getByRole("button", { name: `Stop cadence ${name}` }).click();
  await expect(page.getByText("Cadence stopped.")).toBeVisible();
  await expect(page.getByText(`Cadence ${name} ended: stopped by hand (step 1 of 3)`)).toBeVisible();

  // The recruiter cannot open the Team Lead's page.
  await page.goto("/recruiter/manager/cadences");
  await expect(page.getByRole("heading", { name: "Outreach cadences" })).toHaveCount(0);

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("403"))).toEqual([]);
});
