import { expect, test, type Page } from "@playwright/test";

// rec-004 (AC1, AC2; C1, C2, C5, C7): the seeded recruiter uses "+ Add Recruiter" (company + first contact), adds four more contacts,
// moves the primary and deactivates one; the seeded placement manager reads the same contacts without any write control.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("Add Recruiter creates a company with its primary contact; five contacts, one primary; the manager reads only", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Rec004 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies");
  await page.getByRole("link", { name: "Add recruiter" }).first().click();
  await page.waitForURL("**/recruiter/companies/new?with=contact");
  await expect(page.getByRole("heading", { name: "Add recruiter" })).toBeVisible();

  const first = page.getByRole("group", { name: "Recruiter contact" });
  await first.getByLabel("Contact name (required)").fill("Priya Sharma");
  await first.getByLabel("Designation").fill("TA Manager");
  await first.getByLabel("Role").selectOption({ label: "Talent Acquisition Manager" });
  await first.getByLabel("Mobile").fill("98765 43210");
  await first.getByLabel("Email").fill("priya@e2e-rec004.example.com");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);

  const contacts = page.getByRole("region", { name: "Contacts" });
  const cards = contacts.getByRole("list", { name: "Contacts" }).getByRole("listitem");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText("Priya Sharma");
  await expect(cards.first()).toContainText("Primary");

  // AC1: four more, one of them the HR Manager whose email/phone become §3 HR Email/Phone (C5).
  for (const [person, role] of [["Ravi HR", "HR Manager"], ["Hari Hiring", "Hiring Manager"], ["Rekha Recruiter", "Recruiter"], ["Harish Head", "HR Head"]]) {
    await contacts.getByRole("button", { name: "Add contact" }).click();
    const editor = contacts.getByRole("group", { name: "New contact" });
    await editor.getByLabel("Contact name (required)").fill(person);
    await editor.getByLabel("Role").selectOption({ label: role });
    if (person === "Ravi HR") {
      await editor.getByLabel("Email").fill("ravi@e2e-rec004.example.com");
      await editor.getByLabel("Mobile").fill("90000 00001");
    }
    await editor.getByRole("button", { name: "Save contact" }).click();
    await expect(contacts.getByRole("status")).toHaveText("Contact added.");
  }
  await expect(cards).toHaveCount(5);
  await expect(contacts.getByText("Primary", { exact: true })).toHaveCount(1); // AC2
  await expect(contacts.getByText("ravi@e2e-rec004.example.com").first()).toBeVisible();

  // C2: the primary can't be deactivated while others are active; move it first.
  await contacts.getByRole("button", { name: "Deactivate Priya Sharma" }).click();
  await contacts.getByRole("button", { name: "Yes, deactivate" }).click();
  await expect(contacts.getByRole("alert")).toContainText("Make another contact primary first");
  await contacts.getByRole("button", { name: "Keep active" }).click();
  await contacts.getByRole("button", { name: "Make primary Ravi HR" }).click();
  await expect(contacts.getByRole("status")).toHaveText("Ravi HR is now the primary contact.");
  await expect(cards.first()).toContainText("Ravi HR");
  await contacts.getByRole("button", { name: "Deactivate Priya Sharma" }).click();
  await contacts.getByRole("button", { name: "Yes, deactivate" }).click();
  await expect(contacts.getByRole("status")).toHaveText("Priya Sharma deactivated.");
  await expect(contacts.getByText("Inactive", { exact: true })).toHaveCount(1);
  await expect(contacts.getByText("Primary", { exact: true })).toHaveCount(1);
  const detailUrl = page.url();

  // C1: the manager reads the same contacts and has no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  await expect(cards).toHaveCount(5);
  await expect(contacts.getByRole("button")).toHaveCount(0);
});
