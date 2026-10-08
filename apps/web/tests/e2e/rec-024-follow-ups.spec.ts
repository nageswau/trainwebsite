import { expect, test, type Page } from "@playwright/test";

// rec-024 (AC1-AC3; FU2, FU3, FU9): the seeded recruiter adds two follow-ups to a new company (one about its contact), sees them in the
// daily list's Upcoming tab, marks the earlier one done with an outcome and the company's Next follow-up moves on; the seeded placement
// manager reads the same follow-ups without any write control.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** An IST wall-clock `datetime-local` value `days` from now at 10:30. */
function istInput(days: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));
  return `${day}T10:30`;
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("follow-ups on a company: add, the daily list, done moves the next follow-up; the manager reads only", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Rec024 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new?with=contact");
  await page.getByRole("group", { name: "Recruiter contact" }).getByLabel("Contact name (required)").fill("Priya Sharma");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();

  const details = page.getByRole("region", { name: "Details" });
  await expect(details).toContainText("None scheduled");
  const section = page.getByRole("region", { name: "Follow-ups" });
  await expect(section.getByText("No follow-ups yet.")).toBeVisible();

  // AC3 / positive scenario: a follow-up for JD due tomorrow, about the contact; then a later one.
  for (const [days, reason, contact] of [[1, "Follow-up for JD", "Priya Sharma"], [3, "Contract/MoU", null]] as const) {
    await section.getByRole("button", { name: "Add follow-up" }).click();
    const form = section.getByRole("form", { name: "Add follow-up" });
    await form.getByLabel("Due date and time (IST, required)").fill(istInput(days));
    await form.getByLabel("Reason (required)").selectOption({ label: reason });
    if (contact) await form.getByLabel("Contact").selectOption({ label: contact });
    await form.getByRole("button", { name: "Add follow-up" }).click();
    await expect(section.getByRole("status")).toHaveText("Follow-up added.");
  }
  const items = section.getByRole("list", { name: "Follow-ups" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.first()).toContainText("Follow-up for JD");
  await expect(items.first()).toContainText("Priya Sharma");
  await expect(details).not.toContainText("None scheduled"); // FU9: the earliest open one
  await expect(page.getByRole("region", { name: "Contacts" })).not.toContainText("None scheduled");

  // FU2: both are tomorrow or later, so they sit in Upcoming, not Today.
  await page.goto("/recruiter/follow-ups?due=upcoming");
  const cards = page.getByRole("list", { name: "Follow-ups" }).getByRole("listitem").filter({ hasText: name });
  await expect(cards).toHaveCount(2);
  await page.getByRole("button", { name: /^Today/ }).click();
  await expect(page.getByRole("button", { name: /^Today/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("listitem").filter({ hasText: name })).toHaveCount(0);

  // AC2: completing the earlier one moves the company's next follow-up to the later one.
  await page.goto(detailUrl);
  const firstDue = await details.textContent();
  await items.first().getByRole("button", { name: "Done" }).click();
  await items.first().getByLabel("Outcome (optional)").fill("JD received");
  await items.first().getByRole("button", { name: "Mark done" }).click();
  await expect(section.getByRole("status")).toHaveText("Marked done.");
  await expect(items.last()).toContainText("JD received");
  await expect(details).not.toHaveText(firstDue ?? "");
  await expect(details).not.toContainText("None scheduled");
  await expect(page.getByRole("region", { name: "Contacts" })).toContainText("None scheduled");

  // FU3: the manager reads the same follow-ups and has no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  await expect(items).toHaveCount(2);
  await expect(section.getByRole("button")).toHaveCount(0);
});
