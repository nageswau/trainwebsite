import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-013 (AC1-AC3, WA2-WA4, D3): WhatsApp click-to-chat. A telecaller picks a library template on the lead page, edits the rendered text,
// opens wa.me (the popup carries the lead's number and the edited text), says "Not sent" (nothing logged), then confirms (the "WhatsApp
// sent – date – time" row appears) and deletes it; a lead without a number has the action disabled; the manager reads the log only. wa.me
// is stubbed so the run never leaves the machine.
test.describe.configure({ timeout: 150_000 });

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E WA Manager ${stamp}`, email: `tel013-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E WA Telecaller ${stamp}`, email: `tel013-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `WA-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const template = await page.request.post("/api/v1/telecaller/templates", {
    data: { channel: "whatsapp", kind: "welcome", name: `E2E Welcome ${stamp}`, body: "Hi {name}, thanks for your enquiry." },
  });
  expect(template.status()).toBe(201);
  const leads: string[] = [];
  const phone = `9${String(stamp).slice(-9)}`;
  for (const [i, name] of [`WA Lead ${stamp}`, `No Number Lead ${stamp}`].entries()) {
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name, email: `tel013-${i}-${stamp}@example.com`, phone: i === 0 ? phone : `8${String(stamp).slice(-9)}`, subject: "Python", message: "Please call me." },
    });
    expect(created.status()).toBe(201);
    leads.push((await created.json()).id);
  }
  const assigned = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } });
  expect(assigned.status()).toBe(200);
  const cleared = await page.request.patch(`/api/v1/telecaller/leads/${leads[1]}`, { data: { phone: null } });
  expect(cleared.status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, leads, phone, templateName: `E2E Welcome ${stamp}` };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a telecaller sends a WhatsApp from a template, confirms it and sees it logged; the manager reads it", async ({ page, context }) => {
  const stamp = Date.now();
  const { manager, caller, leads, phone, templateName } = await setup(page, stamp);
  await context.route("https://wa.me/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>wa.me stub</title>" }));
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${leads[0]}`);
  await expect(page.getByRole("heading", { name: `WA Lead ${stamp}` })).toBeVisible();
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Messages", exact: true }) });
  await expect(section.getByText("No messages sent yet.")).toBeVisible();

  // the header's WhatsApp opens the composer; the template renders with the lead's name and stays editable
  await page.getByRole("button", { name: `WhatsApp WA Lead ${stamp}` }).click();
  const composer = page.getByRole("group", { name: "WhatsApp message" });
  await composer.getByLabel("Template").selectOption({ label: templateName });
  const text = composer.getByLabel("Message");
  await expect(text).toHaveValue(`Hi WA Lead ${stamp}, thanks for your enquiry.`);
  await text.fill(`Hi WA Lead ${stamp}, here is the course & fee info?`);

  // AC1: the mobile (no WhatsApp number) with +91, and the edited text URL-encoded; "Not sent" logs nothing (edge case)
  const [popup] = await Promise.all([page.waitForEvent("popup"), composer.getByRole("link", { name: /Open WhatsApp/ }).click()]);
  const url = new URL(popup.url());
  expect(`${url.origin}${url.pathname}`).toBe(`https://wa.me/91${phone}`);
  expect(url.searchParams.get("text")).toBe(`Hi WA Lead ${stamp}, here is the course & fee info?`);
  await popup.close();
  await composer.getByRole("button", { name: "Not sent" }).click();
  await expect(section.getByText("No messages sent yet.")).toBeVisible();

  // AC2: confirming records "WhatsApp sent – date – time" with the template
  const [again] = await Promise.all([page.waitForEvent("popup"), composer.getByRole("link", { name: /Open WhatsApp/ }).click()]);
  await again.close();
  await composer.getByRole("button", { name: "Yes, record as sent" }).click();
  await expect(section.getByText("WhatsApp send recorded.")).toBeVisible();
  const item = section.getByRole("listitem").first();
  await expect(item).toContainText(/WhatsApp sent – \d{1,2} \w{3,4} \d{4} – \d{1,2}:\d{2} (AM|PM)/);
  await expect(item).toContainText(templateName);
  await expect(item).toContainText("course & fee info?");
  await page.reload();
  await expect(section.getByRole("listitem")).toHaveCount(1);
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // AC3: a lead with no number -- the action is disabled and the API refuses
  await page.goto(`/telecaller/leads/${leads[1]}`);
  await expect(section.getByRole("button", { name: "Send WhatsApp" })).toBeDisabled();
  await expect(section.getByText("No WhatsApp or mobile number on this lead.")).toBeVisible();
  await expect(page.getByRole("button", { name: `WhatsApp No Number Lead ${stamp}` })).toHaveCount(0);
  const refused = await page.request.post(`/api/v1/telecaller/leads/${leads[1]}/messages`, { data: { channel: "whatsapp", body: "Hi" } });
  expect(refused.status()).toBe(409);

  // WA2: the manager reads the log without actions
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.goto(`/telecaller/manager/leads/${leads[0]}`);
  await expect(section.getByRole("listitem")).toHaveCount(1);
  await expect(section.getByRole("listitem").first()).toContainText(`E2E WA Telecaller ${stamp}`);
  await expect(section.getByRole("button")).toHaveCount(0);

  // WA3: the sender deletes today's send
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${leads[0]}`);
  await section.getByRole("listitem").first().getByRole("button", { name: "Delete" }).click();
  await section.getByRole("button", { name: "Yes, delete" }).click();
  await expect(section.getByText("Message deleted.")).toBeVisible();
  await expect(section.getByText("No messages sent yet.")).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
