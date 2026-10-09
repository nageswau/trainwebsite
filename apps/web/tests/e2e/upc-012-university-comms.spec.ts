import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-012 (AC1-AC3, P1, N1, E1): the partnership head creates a proposal email and a WhatsApp follow-up template (an unknown placeholder
// is refused); the owning manager logs a call (the contact's last interaction shows -- AC3), sends the WhatsApp only on confirm (AC2) and
// the proposal email from its template, whose delivery status is shown (AC1; "sent" needs the stack's SMTP, otherwise "not delivered" is
// still a status); a contact without an email or number cannot be messaged (E1); a same-team manager reads but cannot write; the page
// fits a phone. Throwaway accounts via the real admin API; wa.me never leaves the machine.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc012-h-${stamp}@example.local` });
  const manager = (n: number) => post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${n} ${stamp}`, email: `upc012-m${n}-${stamp}@example.local`,
    partnership_profile: { employee_id: `U12-${n}-${stamp}`, reporting_head_user_id: head.id },
  });
  const [owner, colleague] = [await manager(1), await manager(2)];
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Comms University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: owner.id });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Priya Raman", email: `priya-${stamp}@abc.ac.uk`, whatsapp: "+91 98450 00000", phone: "+44 20 7000 0000" });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Ravi NoReach" });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, owner, colleague]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, owner, colleague, university };
}

test("upc-012: templates, a call, WhatsApp on confirm and a proposal email on a university", async ({ page, context }) => {
  test.setTimeout(180_000);
  await context.route("https://wa.me/**", (route) => route.fulfill({ status: 200, body: "wa.me" }));
  const stamp = Date.now();
  const { head, owner, colleague, university } = await setUp(page, stamp);
  const uniPath = `/partnership/universities/${university.id}`;

  // the head's library (UC4, UC5)
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.getByRole("link", { name: "Message templates" }).first().click();
  await page.selectOption("#rtpl-new-channel", "email");
  await page.fill("#rtpl-new-name", `Partnership proposal ${stamp}`);
  await page.fill("#rtpl-new-subject", "Proposal for {university}");
  await page.fill("#rtpl-new-body", "Dear {first_name}");
  await page.click("button:has-text('Create template')");
  await expect(page.locator("#rtpl-create-feedback")).toContainText("Unknown placeholder {first_name}"); // N1
  await page.fill("#rtpl-new-body", "Dear {name},\n\nI am {manager} from EduSphere. Please find our partnership proposal for {university}.");
  await page.click("button:has-text('Create template')");
  await expect(page.locator("#rtpl-create-feedback")).toHaveText(`Created Partnership proposal ${stamp}.`);
  await page.selectOption("#rtpl-new-channel", "whatsapp");
  await page.fill("#rtpl-new-name", `Follow-up ${stamp}`);
  await page.fill("#rtpl-new-body", "Hi {name}, {manager} from EduSphere following up on {university}.");
  await page.click("button:has-text('Create template')");
  await expect(page.locator("#rtpl-create-feedback")).toHaveText(`Created Follow-up ${stamp}.`);

  // the owning manager: a call (AC3)
  await signIn(page, "/overseas/login", owner.email, "/partnership/dashboard");
  await page.goto(uniPath);
  await page.getByRole("button", { name: "Log call" }).click();
  const form = page.getByRole("form", { name: "Log call" });
  await form.getByLabel("Contact (required)").selectOption({ label: "Priya Raman" });
  await expect(form.getByRole("link", { name: /Call Priya Raman/ })).toHaveAttribute("href", "tel:+442070000000");
  await form.getByLabel("Outcome (required)").selectOption("connected");
  await form.getByLabel("Notes").fill("Discussed the proposal.");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(page.getByText("Call logged.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Calls" }).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText(/Last interaction:/)).toBeVisible();

  // E1: a contact without an email or a number
  const to = page.getByLabel("To", { exact: true });
  await to.selectOption({ label: "Ravi NoReach" });
  await expect(page.getByRole("button", { name: "Send WhatsApp" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Send email" })).toBeDisabled();
  await to.selectOption({ label: "Priya Raman" });

  // AC2: WhatsApp is logged only on confirm
  await page.getByRole("button", { name: "Send WhatsApp" }).click();
  const wa = page.getByRole("group", { name: "WhatsApp message" });
  await wa.getByLabel("Template").selectOption({ label: `Follow-up ${stamp}` });
  await expect(wa.getByLabel("Message")).toHaveValue(`Hi Priya Raman, E2E Manager 1 ${stamp} from EduSphere following up on ${university.name}.`);
  const [tab] = await Promise.all([page.waitForEvent("popup"), wa.getByRole("link", { name: /Open WhatsApp/ }).click()]);
  expect(tab.url()).toMatch(/^https:\/\/wa\.me\/919845000000\?text=/);
  await tab.close();
  expect((await (await page.request.get(`/api/v1/partnership/universities/${university.id}/messages`)).json()).total).toBe(0);
  await wa.getByRole("button", { name: "Yes, record as sent" }).click();
  await expect(page.getByText("WhatsApp to Priya Raman recorded.")).toBeVisible();

  // P1 + AC1: a proposal email from the template, with its delivery status
  await page.getByRole("button", { name: "Send email" }).click();
  const email = page.getByRole("form", { name: "Email message" });
  await email.getByLabel("Template").selectOption({ label: `Partnership proposal ${stamp}` });
  await expect(email.getByLabel("Subject")).toHaveValue(`Proposal for ${university.name}`);
  await email.getByRole("button", { name: /Send email/ }).click();
  await expect(page.getByText("Email to Priya Raman queued for sending.")).toBeVisible();
  const messages = page.getByRole("list", { name: "Messages" }).getByRole("listitem");
  await expect(messages).toHaveCount(2);
  await expect(messages.first()).toContainText(/^Email (sent|queued|sending|not delivered)/, { timeout: 20_000 });

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // a same-team manager reads the history but cannot write (UC3)
  await signIn(page, "/overseas/login", colleague.email, "/partnership/dashboard");
  await page.goto(uniPath);
  await expect(page.getByRole("list", { name: "Calls" }).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Log call" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send WhatsApp" })).toHaveCount(0);
});
