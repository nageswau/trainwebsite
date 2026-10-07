import { test, expect, type Page } from "@playwright/test";

// tel-004 -- the lead pipeline on the admin lead panel: valid moves only, a reason to close and to reopen, and the stage history.
// Requires the stack running; each test submits its own throwaway enquiry through the public API.

async function signInAsItAdmin(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

async function leadRow(page: Page, name: string) {
  await page.goto(`/it/admin/leads?q=${encodeURIComponent(name)}`);
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage leads" }) });
  const row = panel.locator("tr", { hasText: name });
  await expect(row).toBeVisible();
  return row;
}

test("admin closes a lead with a reason, reopens it, and reads the history", async ({ page, request }) => {
  test.setTimeout(30_000); // two moves, a reload and the history: 15 s ran out with 6 parallel workers on one API (tel-007 browser QA)
  const name = `E2E Pipeline ${Date.now()}`;
  const created = await request.post("/api/v1/public/enquiries", {
    data: { division: "it", name, email: `pipe-${Date.now()}@example.com`, subject: "Python", message: "Interested." },
  });
  expect(created.ok()).toBeTruthy();
  // tel-007 DI2: the enquiry is distributed on arrival when an IT telecaller is eligible (a system New Lead -> Assigned row first).
  // tel-005 I3: the public reply's status is a constant acknowledgement, so the stage is read from the stored lead.
  await signInAsItAdmin(page);
  const stored = (await (await page.request.get(`/api/v1/admin/leads?q=${encodeURIComponent(name)}`)).json()).items[0];
  const assigned = stored.status === "assigned";
  const first = assigned ? "Assigned" : "New Lead";
  const row = await leadRow(page, name);
  await expect(row).toContainText(first);

  await row.getByRole("button", { name: `Change stage for ${name}` }).click();
  const select = row.getByLabel(`New stage for ${name}`);
  await expect(select.locator("option", { hasText: "Converted" })).toHaveCount(0); // T5: never chosen by a person
  await expect(select.locator("option", { hasText: "Contacted" })).toHaveCount(0); // system stage
  await select.selectOption("not_interested");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row.getByRole("alert")).toHaveText("Add a reason for this stage.");
  await row.getByLabel("Reason (required)").fill("Chose a different course");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row.getByRole("status")).toHaveText("Stage updated.");
  await expect(row).toContainText("Not Interested");

  await row.getByRole("button", { name: `Change stage for ${name}` }).click();
  await row.getByLabel(`New stage for ${name}`).selectOption({ label: "Reopen to Follow-up" });
  await row.getByLabel("Reason (required)").fill("Asked for a call back");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row).toContainText("Follow-up");

  await page.reload(); // the stage is stored, not just shown
  const reloaded = await leadRow(page, name);
  await expect(reloaded).toContainText("Follow-up");
  // tel-015 TM1: History is the merged timeline, newest first -- the stage rows among the other entries
  await reloaded.getByRole("button", { name: `History for ${name}` }).click();
  const list = reloaded.getByRole("list", { name: `History for ${name}` });
  const stages = list.getByRole("listitem").filter({ hasText: "Stage:" });
  await expect(stages).toHaveCount(assigned ? 3 : 2);
  await expect(stages.nth(0)).toContainText("Not Interested → Follow-up");
  await expect(stages.nth(1)).toContainText(`${first} → Not Interested`);
  await expect(stages.nth(1)).toContainText("Chose a different course");
  if (assigned) await expect(stages.nth(2)).toContainText("New Lead → Assigned");
  await expect(list.getByRole("listitem").last()).toContainText("Lead created");
});

test("the Stage filter lists the pipeline by label", async ({ page }) => {
  await signInAsItAdmin(page);
  await page.goto("/it/admin/leads");
  const stage = page.getByLabel("Stage", { exact: true });
  await expect(stage.locator("option")).toHaveCount(17); // All stages + 16
  await stage.selectOption({ label: "First Call Pending" });
  await expect(page).toHaveURL(/status=first_call_pending/);
});

test("the stage API refuses a signed-out caller and a non-telecaller role", async ({ request, page }) => {
  const url = "/api/v1/telecaller/leads/00000000-0000-0000-0000-000000000000/stage";
  expect((await request.post(url, { data: { to_stage: "qualified" } })).status()).toBe(401);
  await signInAsItAdmin(page);
  expect((await page.request.post(url, { data: { to_stage: "qualified" } })).status()).toBe(403);
});
