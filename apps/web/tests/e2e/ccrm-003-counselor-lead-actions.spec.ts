import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-003 (DEC-SCOPE-243): a counselor works a lead handed to them -- an open stage move needs a next action (A2), the CC8 list only
// (A1), a follow-up is added and completed (A4), closing as Lost needs a reason, cancels the open follow-up and still confirms (QA-03);
// another counselor is 404. Throwaway accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 240_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const istInput = (hoursAhead: number) => new Date(Date.now() + (5.5 + hoursAhead) * 3_600_000).toISOString().slice(0, 16);

test("counselor sets a next action, moves the stage, works a follow-up and closes the lead", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E LA Manager ${stamp}`, email: `ccrm003-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E LA Telecaller ${stamp}`, email: `ccrm003-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `LA-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E LA Counselor ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `ccrm003-c-${stamp}@example.local` });
  const other = await post({ role: "counselor", division: "it", full_name: `E2E LA Other ${stamp}`, email: `ccrm003-o-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, counselor, other]) await activateWithToken(page.request, user.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller creates the lead and hands it over
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name: `LA Lead ${stamp}`, email: `ccrm003-l-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  const handed = await page.request.post(`/api/v1/telecaller/leads/${id}/handover`, { data: { counselor_id: counselor.id } });
  expect(handed.status(), await handed.text()).toBe(200);

  // the counselor: an open move without a next action is refused, in the API's words
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/leads/${id}`);
  const lead = `LA Lead ${stamp}`;
  await expect(page.getByText("No next action set. Add one before moving the lead to an open stage.")).toBeVisible();
  await page.getByRole("button", { name: `Change stage for ${lead}` }).click();
  const stage = page.getByLabel(`New stage for ${lead}`);
  await expect(stage.locator("option")).toHaveText(["Choose a stage", "Qualified", "Follow-up", "Counselling Scheduled", "Counselling Completed",
    "Not Interested", "Not Eligible", "Lost"]);
  await stage.selectOption("counselling_completed");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Set a next action and its due date first")).toBeVisible();

  // set the next action, then the move goes through
  await page.getByRole("button", { name: "Set next action" }).click();
  await page.getByLabel("Action", { exact: true }).fill("Send the course shortlist");
  await page.getByLabel("Due date").fill(new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Save next action" }).click();
  await expect(page.getByText("Next action saved.")).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await expect(page.getByText("Stage: Counselling Completed", { exact: true })).toBeVisible();

  // a follow-up, added and done
  const followUps = page.getByRole("region", { name: "Follow-ups" });
  await followUps.getByRole("button", { name: "Add follow-up" }).click();
  await expect(page.getByLabel("Also move the lead to Follow-up")).toHaveCount(0);
  await page.getByLabel("Due date and time (IST, required)").fill(istInput(2));
  await page.getByLabel("Reason (required)").selectOption("fee_details");
  await page.getByRole("form", { name: "Add follow-up" }).getByRole("button", { name: "Add follow-up" }).click();
  await expect(followUps.getByText("Follow-up added.")).toBeVisible();
  await followUps.getByRole("button", { name: "Done" }).click();
  await expect(followUps.getByText("Marked done.")).toBeVisible();

  // a second, open follow-up for the close to cancel
  await followUps.getByRole("button", { name: "Add follow-up" }).click();
  await page.getByLabel("Due date and time (IST, required)").fill(istInput(1));
  await page.getByLabel("Reason (required)").selectOption("counselor_call");
  await page.getByRole("form", { name: "Add follow-up" }).getByRole("button", { name: "Add follow-up" }).click();
  await expect(followUps.getByText("Follow-up added.")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // closing as Lost needs a reason, cancels the open follow-up and still confirms (QA-03)
  await page.getByRole("button", { name: `Change stage for ${lead}` }).click();
  await page.getByLabel(`New stage for ${lead}`).selectOption("lost");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Add a reason for this stage.")).toBeVisible();
  await page.getByLabel("Reason (required)").fill("Chose another institute");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await expect(page.getByRole("button", { name: `Change stage for ${lead}` })).toHaveCount(0);
  await expect(followUps.getByRole("button", { name: "Add follow-up" })).toHaveCount(0);
  await expect(followUps).toContainText("Lead closed");

  // another counselor: 404
  await signIn(page, "it", other.email, E2E_PASSWORD, "/it/counselor/dashboard");
  expect((await page.request.post(`/api/v1/counselor/leads/${id}/stage`, { data: { to_stage: "qualified" } })).status()).toBe(404);

  // the one deliberate refusal above (a move with no next action) is the browser's own 422 resource log; nothing else
  expect(consoleErrors).toEqual(["Failed to load resource: the server responded with a status of 422 (Unprocessable Entity)"]);
});
