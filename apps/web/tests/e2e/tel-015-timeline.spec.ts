import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-015 (DEC-SCOPE-114): the merged lead timeline. An IT telecaller's lead gathers a WhatsApp send, a follow-up and a call logged on the
// page (the timeline re-reads without a reload); after the handover the counselor and the IT admin read the same entries. Throwaway
// accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("the lead timeline for the telecaller, the counselor and the admin", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E TL Manager ${stamp}`, email: `tel015-m-${stamp}@example.local` });
  const callerName = `E2E TL Telecaller ${stamp}`;
  const caller = await post({
    role: "telecaller", full_name: callerName, email: `tel015-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `TL-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E TL Counselor ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `tel015-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await activateWithToken(page.request, counselor.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller's lead: created, a WhatsApp send and a follow-up through the API
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const name = `TL Lead ${stamp}`;
  const phone = `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name, email: `tel015-l-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  const lead = (path: string, data: object) => page.request.post(`/api/v1/telecaller/leads/${id}${path}`, { data });
  expect((await lead("/messages", { channel: "whatsapp", body: "Hello! Here are the Cyber Security batch dates." })).status()).toBe(201);
  const due = new Date(Date.now() + 2 * 86_400_000).toISOString();
  expect((await lead("/follow-ups", { due_at: due, reason: "fee_details", notes: "Send the fee sheet" })).status()).toBe(201);

  await page.goto(`/telecaller/leads/${id}`);
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity.getByText("Follow-up scheduled: Need fee details")).toBeVisible();
  await expect(activity.getByText("WhatsApp sent")).toBeVisible();
  await expect(activity.getByText("Hello! Here are the Cyber Security batch dates.")).toBeVisible();
  await expect(activity.getByRole("listitem").last()).toContainText("Lead created");
  await expect(activity.getByRole("listitem").last()).toContainText(callerName);

  // a call logged on the page appears at once (D8: the timeline re-reads on a change)
  const calls = page.locator("section", { has: page.getByRole("heading", { name: "Calls", exact: true }) });
  await calls.getByRole("button", { name: "Log call" }).click();
  const form = page.getByRole("form", { name: "Log call" });
  await form.getByLabel("Outcome (required)").selectOption("interested");
  await form.getByLabel("Remarks").fill("Keen on the weekend batch");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged.")).toBeVisible();
  await expect(activity.getByText("Outgoing call: Interested")).toBeVisible();
  await expect(activity.getByText("Keen on the weekend batch")).toBeVisible();
  for (const width of [390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // the handover; the counselor reads the same history, including the telecaller's call (AC2)
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByText(`Handed over to ${counselorName}.`)).toBeVisible();
  await expect(activity.getByText(`Handed over to ${counselorName}`)).toBeVisible();
  await expect(activity.getByText("Follow-up cancelled: Need fee details")).toBeVisible(); // tel-018: the handover cancels it, by System

  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/leads/${id}`);
  const counselorView = page.getByRole("list", { name: "Lead activity" });
  await expect(counselorView.getByText("Outgoing call: Interested")).toBeVisible();
  await expect(counselorView.getByText(`Handed over to ${counselorName}`)).toBeVisible();

  // the IT admin's History shows the merged timeline
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  await page.goto(`/it/admin/leads?q=${encodeURIComponent(name)}`);
  const row = page.locator("tr", { hasText: name });
  await row.getByRole("button", { name: `History for ${name}` }).click();
  const history = row.getByRole("list", { name: `History for ${name}` });
  await expect(history.getByText("Outgoing call: Interested")).toBeVisible();
  await expect(history.getByRole("listitem").last()).toContainText("Lead created");

  expect(consoleErrors).toEqual([]);
});
