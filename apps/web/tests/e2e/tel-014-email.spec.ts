import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-014 (AC1-AC3, EM1-EM4, E1-E3): email to a lead. The first test needs no mail server: a telecaller's composer renders a library email
// template (subject and body, both editable), a lead without an address has the action disabled and the API refuses, and the manager
// reads without actions. The @external test needs the worker and a Mailpit SMTP sink with chaos enabled (MAILPIT_URL, the QA stack): the
// email is queued, delivered (AC1 -- rendered placeholders, the telecaller's name and Reply-To) and its row moves to "Email sent"; a
// recipient the server rejects shows "Email failed" (AC2).
test.describe.configure({ timeout: 180_000 });

const MAILPIT = process.env.MAILPIT_URL ?? "http://host.docker.internal:8214";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Mail Manager ${stamp}`, email: `tel014-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Mail Telecaller ${stamp}`, email: `tel014-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `EM-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const template = await page.request.post("/api/v1/telecaller/templates", {
    data: { channel: "email", kind: "follow_up", name: `E2E Follow-up ${stamp}`, subject: "Next steps for {name}",
      body: "Hi {name},\nThanks for your enquiry. Reply to this email with a good time to talk." },
  });
  expect(template.status()).toBe(201);
  const leads: { id: string; email: string }[] = [];
  for (const [i, name] of [`Mail Lead ${stamp}`, `No Email Lead ${stamp}`, `Bounce Lead ${stamp}`].entries()) {
    const email = `tel014-${i}-${stamp}@example.com`;
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name, email, phone: `9${String(stamp + i).slice(-9)}`, subject: "Python", message: "Please email me." },
    });
    expect(created.status()).toBe(201);
    leads.push({ id: (await created.json()).id, email });
  }
  const assigned = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads.map((l) => l.id), telecaller_user_id: caller.id } });
  expect(assigned.status()).toBe(200);
  const cleared = await page.request.patch(`/api/v1/telecaller/leads/${leads[1].id}`, { data: { email: null } });
  expect(cleared.status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, leads, templateName: `E2E Follow-up ${stamp}` };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const messages = (page: Page) => page.locator("section", { has: page.getByRole("heading", { name: "Messages", exact: true }) });

test("a telecaller's email composer renders a template; no address disables it; the manager can't send", async ({ page }) => {
  const stamp = Date.now();
  const { manager, caller, leads, templateName } = await setup(page, stamp);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${leads[0].id}`);
  await expect(page.getByRole("heading", { name: `Mail Lead ${stamp}` })).toBeVisible();
  const section = messages(page);
  await expect(section.getByText("No messages sent yet.")).toBeVisible();

  // the header's Email opens the composer; the template renders subject and body with the lead's name, both editable (EM4)
  await page.getByRole("button", { name: `Email Mail Lead ${stamp}` }).click();
  const composer = page.getByRole("form", { name: "Email message" });
  await expect(composer.getByLabel("Template")).toBeFocused();
  await expect(composer.getByRole("button", { name: "Send email" })).toBeDisabled();
  await composer.getByLabel("Template").selectOption({ label: templateName });
  await expect(composer.getByLabel("Subject")).toHaveValue(`Next steps for Mail Lead ${stamp}`);
  await expect(composer.getByLabel("Message")).toHaveValue(`Hi Mail Lead ${stamp},\nThanks for your enquiry. Reply to this email with a good time to talk.`);
  await expect(composer.getByRole("button", { name: "Send email" })).toBeEnabled();
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await composer.getByRole("button", { name: "Cancel" }).click();
  await expect(section.getByRole("button", { name: "Send email" })).toBeFocused();

  // AC3: no address -- disabled with its reason, no header button, and the API refuses
  await page.goto(`/telecaller/leads/${leads[1].id}`);
  await expect(section.getByRole("button", { name: "Send email" })).toBeDisabled();
  await expect(section.getByText("No email address on this lead.")).toBeVisible();
  await expect(page.getByRole("button", { name: `Email No Email Lead ${stamp}` })).toHaveCount(0);
  const refused = await page.request.post(`/api/v1/telecaller/leads/${leads[1].id}/messages`, { data: { channel: "email", subject: "Hi", body: "Hi" } });
  expect([409, 503]).toContain(refused.status()); // 409 no address; 503 first where the stack has no SMTP (E3)

  // E1: the manager reads the lead without Send email
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.goto(`/telecaller/manager/leads/${leads[0].id}`);
  await expect(section.getByText("No messages sent yet.")).toBeVisible();
  await expect(section.getByRole("button")).toHaveCount(0);
  const managerSend = await page.request.post(`/api/v1/telecaller/leads/${leads[0].id}/messages`, { data: { channel: "email", subject: "Hi", body: "Hi" } });
  expect(managerSend.status()).toBe(403);

  expect(consoleErrors).toEqual([]);
});

async function mailpitSearch(request: APIRequestContext, to: string) {
  const found = await (await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
  return found.messages as { ID: string }[];
}

test("@external an email is delivered through SMTP and its row reaches Email sent; a rejected recipient shows Email failed", async ({ page }) => {
  const stamp = Date.now();
  const { caller, leads, templateName } = await setup(page, stamp);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${leads[0].id}`);
  const section = messages(page);
  await section.getByRole("button", { name: "Send email" }).click();
  const composer = page.getByRole("form", { name: "Email message" });
  await composer.getByLabel("Template").selectOption({ label: templateName });
  await expect(composer.getByLabel("Subject")).toHaveValue(`Next steps for Mail Lead ${stamp}`);
  await composer.getByLabel("Subject").fill(`Next steps for Mail Lead ${stamp} – Python`);
  await composer.getByRole("button", { name: "Send email" }).click();
  await expect(section.getByText("Email queued for sending.")).toBeVisible();
  const item = section.getByRole("listitem").first();
  await expect(item).toContainText(/Email (sending|sent) – \d{1,2} \w{3,4} \d{4} – \d{1,2}:\d{2} (AM|PM)/);
  await expect(item).toContainText(/Email sent – /, { timeout: 30_000 }); // the list refreshes while it is sending
  await expect(item).toContainText(templateName);
  await expect(item).toContainText(`Next steps for Mail Lead ${stamp} – Python`);
  await expect(item.getByRole("button")).toHaveCount(0); // EM2: never deleted

  // AC1 / EM1: delivered to the lead's address with the placeholders filled, in the telecaller's name, replies to the telecaller
  const [found] = await mailpitSearch(page.request, leads[0].email);
  expect(found, "the email reached the SMTP server").toBeTruthy();
  const mail = await (await page.request.get(`${MAILPIT}/api/v1/message/${found.ID}`)).json();
  expect(mail.Subject).toBe(`Next steps for Mail Lead ${stamp} – Python`);
  expect(mail.From.Name).toBe(`E2E Mail Telecaller ${stamp} via EduSphere`);
  expect(mail.ReplyTo[0].Address).toBe(caller.email);
  expect(mail.Text).toContain(`Hi Mail Lead ${stamp},`);
  expect(mail.HTML).toContain("Thanks for your enquiry.");

  // AC2: the SMTP server rejects the recipient (Mailpit chaos, 550) -- the row shows Email failed
  const chaos = await page.request.put(`${MAILPIT}/api/v1/chaos`, { data: { Recipient: { ErrorCode: 550, Probability: 100 } } });
  expect(chaos.ok(), "Mailpit must run with MP_ENABLE_CHAOS=true").toBe(true);
  try {
    await page.goto(`/telecaller/leads/${leads[2].id}`);
    await section.getByRole("button", { name: "Send email" }).click();
    await composer.getByLabel("Subject").fill("Your brochure");
    await composer.getByLabel("Message").fill("Hi, here is the brochure.");
    await composer.getByRole("button", { name: "Send email" }).click();
    const failed = section.getByRole("listitem").first();
    await expect(failed).toContainText(/Email failed – /, { timeout: 30_000 });
    await expect(failed).toContainText("This email was not delivered.");
    await expect(failed).toContainText("Custom message");
  } finally {
    await page.request.put(`${MAILPIT}/api/v1/chaos`, { data: {} });
  }

  expect(consoleErrors).toEqual([]);
});
