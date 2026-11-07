import { expect, test, type Page } from "@playwright/test";

// pob-005 (DEC-SCOPE-411): the seeded recruiter marks a decision-maker, sees a message move the contact to Contacted and a logged reply
// move them to Replied (AC1), the contact's own Activity, a duplicate warning across companies (AC3), and Do Not Contact refusing a send
// (AC2) and dropping the person from the recipients; no sideways scroll on a phone.
const RECRUITER = "placement@edusphere.local";
const mobile = () => "9" + String(Math.floor(1e8 + Math.random() * 9e8));
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", RECRUITER);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function company(page: Page, prefix: string, contact: Record<string, unknown>) {
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name: `${prefix} ${Date.now()} Pvt`, contact: { is_primary: true, ...contact } } });
  expect(created.status(), await created.text()).toBe(201);
  return (await created.json()).company as { id: string; name: string };
}

test("contact status moves with outreach, Do Not Contact blocks sends, duplicates warn", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page);
  const shared = mobile();
  const other = await company(page, "POB5 Other", { name: "Old Asha", mobile: shared });
  const mine = await company(page, "POB5", { name: "Priya HR", mobile: mobile() });
  await page.goto(`/recruiter/companies/${mine.id}`);
  const contacts = page.getByRole("region", { name: "Contacts", exact: true });
  await expect(contacts.getByText("Not contacted", { exact: true })).toBeVisible();

  // AC4: decision-maker and source
  await contacts.getByRole("button", { name: "Edit Priya HR", exact: true }).click();
  await contacts.getByLabel("Decision-maker").check();
  await contacts.getByLabel("Source").selectOption("referral");
  await contacts.getByRole("button", { name: "Save contact" }).click();
  await expect(contacts.getByText("Contact updated.")).toBeVisible();
  await expect(contacts.getByText("Decision-maker", { exact: true })).toBeVisible();

  // AC1: a message -> Contacted; a logged reply -> Replied
  const priya = (await (await page.request.get(`/api/v1/recruiter/companies/${mine.id}/contacts`)).json()).items[0];
  const sent = await page.request.post("/api/v1/recruiter/messages", { data: { channel: "whatsapp", contact_id: priya.id, body: "Hello" } });
  expect(sent.status()).toBe(201);
  await page.reload();
  await expect(page.getByRole("region", { name: "Contacts", exact: true }).getByText("Contacted", { exact: true })).toBeVisible();
  const messages = page.getByRole("region", { name: "Messages", exact: true });
  await messages.getByRole("button", { name: "Log reply from Priya HR" }).click();
  await expect(messages.getByText(/^Reply received – /)).toBeVisible();
  await page.reload();
  const list = page.getByRole("region", { name: "Contacts", exact: true });
  await expect(list.getByText("Replied", { exact: true })).toBeVisible();
  await list.getByRole("button", { name: "Activity Priya HR" }).click();
  const timeline = list.getByRole("list", { name: "Timeline with Priya HR" });
  await expect(timeline.getByText("Status: Contacted → Replied")).toBeVisible();
  await expect(timeline.getByText("WhatsApp reply received")).toBeVisible();

  // AC3: the same mobile at another company warns before saving
  await list.getByRole("button", { name: "Add contact" }).click();
  await list.getByLabel("Contact name (required)").fill("Ravi Dup");
  await list.getByLabel("Mobile").fill(shared);
  await list.getByRole("button", { name: "Save contact" }).click();
  await expect(list.getByText(`Old Asha at ${other.name} (mobile)`)).toBeVisible();
  await list.getByRole("button", { name: "Save anyway" }).click();
  await expect(list.getByText("Contact added.")).toBeVisible();

  // AC2: Do Not Contact refuses a send and leaves the recipients
  await list.getByRole("button", { name: "Edit Ravi Dup", exact: true }).click();
  await list.getByLabel("Status").selectOption("do_not_contact");
  await list.getByRole("button", { name: "Save contact" }).click();
  await expect(list.getByText(/meeting invites to Ravi Dup are blocked/)).toBeVisible();
  const ravi = (await (await page.request.get(`/api/v1/recruiter/companies/${mine.id}/contacts`)).json()).items.find((c: { name: string }) => c.name === "Ravi Dup");
  const refused = await page.request.post("/api/v1/recruiter/messages", { data: { channel: "whatsapp", contact_id: ravi.id, body: "Hi" } });
  expect(refused.status()).toBe(409);
  await page.reload();
  const to = page.getByRole("region", { name: "Messages", exact: true }).getByLabel("To");
  await expect(to.locator("option", { hasText: "Priya HR" })).toHaveCount(1);
  await expect(to.locator("option", { hasText: "Ravi Dup" })).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("region", { name: "Contacts", exact: true })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
