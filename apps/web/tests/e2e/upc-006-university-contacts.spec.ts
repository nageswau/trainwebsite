import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-006 (AC1-AC3, P1, N1, CT11): the owning manager adds contacts (the first becomes primary), moves the primary, edits, sees a 422
// on its field, sets the university's relationship strength and finds it by the list filter; overseas_admin sees only the shareable
// contact and no edit controls; the contacts fit a phone. Throwaway accounts via the real admin API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/overseas/login");
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
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc006-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc006-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U6-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E OA ${stamp}`, email: `upc006-oa-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Contacts University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, admin, university };
}

async function addContact(page: Page, fields: Record<string, string>, options: { shareable?: boolean; primary?: boolean } = {}) {
  await page.getByRole("button", { name: "Add contact" }).click();
  const editor = page.getByRole("group", { name: "New contact" });
  for (const [labelText, value] of Object.entries(fields)) {
    const field = editor.getByLabel(labelText, { exact: true });
    if ((await field.evaluate((el) => el.tagName)) === "SELECT") await field.selectOption(value);
    else await field.fill(value);
  }
  if (options.shareable) await editor.getByLabel("Visible to counsellors (shareable)").check();
  if (options.primary) await editor.getByLabel("Make this the primary contact").check();
  await editor.getByRole("button", { name: "Save contact" }).click();
  await expect(page.getByRole("status")).toHaveText("Contact added.");
}

test("the owning manager keeps contacts; overseas_admin sees the shareable slice", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const { manager, admin, university } = await setUp(page, stamp);
  const detail = `/partnership/universities/${university.id}`;

  await signIn(page, manager.email, "/partnership/dashboard");
  await page.goto(detail);
  const contacts = page.getByRole("region", { name: "Contacts" });
  await expect(contacts.getByText("No contacts recorded yet.")).toBeVisible();

  // P1 + AC1: the first contact becomes primary.
  await addContact(page, {
    "Name (required)": "Priya Raman", Designation: "Regional Manager – India", Role: "regional_manager", Email: "priya@abc.ac.uk",
    WhatsApp: "+91 98450 00000", LinkedIn: "linkedin.com/in/priya-raman", "Preferred communication": "whatsapp", "Relationship strength": "strategic",
  }, { shareable: true });
  const priya = contacts.getByRole("listitem").filter({ hasText: "Priya Raman" });
  await expect(priya.getByText("Primary")).toBeVisible();
  await expect(priya.getByText("Strategic")).toBeVisible();
  await expect(priya.getByRole("link", { name: "https://linkedin.com/in/priya-raman" })).toBeVisible();

  // N1: an invalid email lands on its field and the entry is kept.
  await page.getByRole("button", { name: "Add contact" }).click();
  const editor = page.getByRole("group", { name: "New contact" });
  await editor.getByLabel("Name (required)").fill("Ben Finance");
  await editor.getByLabel("Email", { exact: true }).fill("ben@");
  await editor.getByRole("button", { name: "Save contact" }).click();
  await expect(editor.getByText("Enter a valid email address")).toBeVisible();
  await expect(editor.getByLabel("Name (required)")).toHaveValue("Ben Finance");
  await editor.getByLabel("Email", { exact: true }).fill("ben@abc.ac.uk");
  await editor.getByLabel("Role").selectOption("finance_contact");
  await editor.getByLabel("Notes (internal)").fill("Internal remark");
  await editor.getByRole("button", { name: "Save contact" }).click();
  await expect(page.getByRole("status")).toHaveText("Contact added.");

  // Move the primary, and the refreshed list puts it first.
  await page.getByRole("button", { name: "Make Ben Finance primary" }).click();
  await expect(page.getByRole("status")).toHaveText("Primary contact changed.");
  await expect(contacts.getByRole("listitem").first()).toContainText("Ben Finance");
  await expect(contacts.getByRole("listitem").first()).toContainText("Primary");

  // The primary cannot be deleted while another contact remains.
  await page.getByRole("button", { name: "Delete Ben Finance" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(contacts.getByRole("alert")).toContainText("Make another contact primary");

  // CT11: the university's relationship strength, its badge and the list filter.
  await page.goto(`${detail}/edit`);
  await page.getByLabel("Relationship strength").selectOption("strong");
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`${detail}$`));
  await expect(page.getByText("Relationship: Strong")).toBeVisible();
  await page.goto("/partnership/universities?manager=me&relationship_strength=strong");
  await expect(page.getByRole("link", { name: university.name })).toBeVisible();
  await page.goto("/partnership/universities?manager=me&relationship_strength=dormant");
  await expect(page.getByRole("link", { name: university.name })).toHaveCount(0);

  // Phone width: contacts are blocks, no sideways scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(detail);
  await expect(priya).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.request.post("/api/v1/auth/logout");

  // AC3: overseas_admin sees only the shareable contact, no notes, no edit controls.
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, admin.email, "/overseas/admin/dashboard");
  await page.goto(detail);
  await expect(priya).toBeVisible();
  await expect(contacts.getByText("Ben Finance")).toHaveCount(0);
  await expect(contacts.getByText("Internal remark")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add contact" })).toHaveCount(0);
});
