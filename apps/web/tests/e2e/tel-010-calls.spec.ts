import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-010 (AC1-AC4, CL2-CL4, D3/D4/D10): call logging. A telecaller logs a not-connected call (the lead moves to First Call Pending), then a
// call-back with its required next follow-up (Contacted + a follow-up), edits and deletes a call, sees the follow-up card's Last call and
// closes a lead with Not Interested (no further calls); the manager reads the calls without actions. Like tel-011, the leads are assigned
// through tel-007's API so this run's telecaller has them.
test.describe.configure({ timeout: 150_000 });

const IST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" });
const istDay = (offsetDays: number) => IST_DAY.format(new Date(Date.now() + offsetDays * 86_400_000));
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Call Manager ${stamp}`, email: `tel010-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Call Telecaller ${stamp}`, email: `tel010-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `CL-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const leads: string[] = [];
  for (const [i, name] of [`Call Lead ${stamp}`, `Closing Call Lead ${stamp}`].entries()) {
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name, email: `tel010-${i}-${stamp}@example.com`, phone: `7${String(stamp).slice(-8)}${i}`, subject: "Python", message: "Call me." },
    });
    expect(created.status()).toBe(201);
    leads.push((await created.json()).id);
  }
  const assigned = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } });
  expect(assigned.status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, leads };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a telecaller logs calls with their pipeline effects and follow-up, edits and deletes one; the manager reads them", async ({ page }) => {
  const stamp = Date.now();
  const { manager, caller, leads } = await setup(page, stamp);
  const tomorrow = istDay(1);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${leads[0]}`);
  await expect(page.getByRole("heading", { name: `Call Lead ${stamp}` })).toBeVisible();
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Calls", exact: true }) });
  await expect(section.getByText("No calls logged yet.")).toBeVisible();

  // a not-connected call: the lead's first-call stage moves (AC1)
  await section.getByRole("button", { name: "Log call" }).click();
  const form = page.getByRole("form", { name: "Log call" });
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(form.getByText("Choose an outcome")).toBeVisible();
  await form.getByLabel("Outcome (required)").selectOption("no_answer");
  await form.getByLabel("Remarks").fill("Rang out twice");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(section.getByText("Call logged.")).toBeVisible();
  await expect(page.getByText(/Stage: First Call Pending · Priority:/)).toBeVisible();
  await expect(section.getByRole("listitem").first()).toContainText("No Answer");
  await expect(section.getByRole("listitem").first()).toContainText("Not connected");

  // a call-back needs its next follow-up (D4); the call moves the lead to Contacted and adds the follow-up (AC3)
  await section.getByRole("button", { name: "Log call" }).click();
  await form.getByLabel("Outcome (required)").selectOption("call_back_requested");
  await form.getByLabel("Minutes").fill("3");
  await form.getByLabel("Seconds").fill("20");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(form.getByText("Choose a due date and time")).toBeVisible();
  await form.getByLabel(/Follow-up due/).fill(`${tomorrow}T16:00`);
  await form.getByLabel("Follow-up reason").selectOption("fee_details");
  await form.getByLabel("Next action").fill("Send the fee sheet, then call");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(section.getByText("Call logged.")).toBeVisible();
  await expect(page.getByText(/Stage: Contacted · Priority:/)).toBeVisible();
  await expect(section.getByRole("listitem").first()).toContainText("Call Back Requested");
  await expect(section.getByRole("listitem").first()).toContainText("3 min 20 s");
  const followUps = page.locator("section", { has: page.getByRole("heading", { name: "Follow-ups", exact: true }) });
  await expect(followUps.getByRole("listitem").first()).toContainText("Need fee details");

  // CL4: edit today's call; delete one (its stage move stays)
  await section.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  const edit = page.getByRole("form", { name: "Edit call" });
  await expect(edit.getByLabel("Outcome (required)")).toHaveCount(0);
  await edit.getByLabel("Remarks").fill("Mother asked for a call-back");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(section.getByText("Call updated.")).toBeVisible();
  await expect(section.getByRole("listitem").first()).toContainText("Mother asked for a call-back");
  await section.getByRole("listitem").nth(1).getByRole("button", { name: "Delete" }).click();
  await section.getByRole("button", { name: "Yes, delete" }).click();
  await expect(section.getByText("Call deleted.")).toBeVisible();
  await expect(section.getByRole("listitem")).toHaveCount(1);
  await page.reload();
  await expect(page.getByText(/Stage: Contacted · Priority:/)).toBeVisible();
  await expect(section.getByRole("listitem")).toHaveCount(1);
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // D10: the §7 card shows the last call
  await page.goto(`/telecaller/follow-ups?day=${tomorrow}`);
  const card = page.getByRole("list", { name: "Follow-ups" }).getByRole("listitem").first();
  await expect(card).toContainText("Last call");
  await expect(card).toContainText("Call Back Requested");

  // AC4: the day counts agree
  const counts = await (await page.request.get("/api/v1/telecaller/calls/day-counts")).json();
  expect(counts).toMatchObject({ total: 1, connected: 1, not_connected: 0 });
  expect(counts.by_outcome.call_back_requested).toBe(1);

  // a closing outcome closes the lead; no further call is offered (CL2)
  await page.goto(`/telecaller/leads/${leads[1]}`);
  await section.getByRole("button", { name: "Log call" }).click();
  await form.getByLabel("Outcome (required)").selectOption("not_interested");
  await expect(form.getByText(/closes the lead as Not Interested/)).toBeVisible();
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(section.getByText("Call logged.")).toBeVisible();
  await expect(page.getByText(/Stage: Not Interested · Priority:/)).toBeVisible();
  await expect(section.getByRole("button", { name: "Log call" })).toHaveCount(0);
  const refused = await page.request.post(`/api/v1/telecaller/leads/${leads[1]}/calls`, { data: { duration_seconds: 0, call_type: "outgoing", outcome: "busy" } });
  expect(refused.status()).toBe(409);

  // D8: the manager reads the calls without actions
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.goto(`/telecaller/manager/leads/${leads[0]}`);
  await expect(section.getByRole("listitem")).toHaveCount(1);
  await expect(section.getByRole("listitem").first()).toContainText(`E2E Call Telecaller ${stamp}`);
  await expect(section.getByRole("button")).toHaveCount(0);

  expect(consoleErrors).toEqual([]);
});
