import { expect, test, type Page } from "@playwright/test";

// rec-032 (AC1-AC3; DB1-DB10): the seeded recruiter's dashboard shows the fourteen §1 tiles; a new company moves "New Recruiter Leads"
// by one; a tile opens its list; the skill box opens Find Candidates. The seeded placement manager narrows the dashboard to one recruiter
// and gets no scheduling quick actions. The shared database keeps every earlier run's rows, so figures are compared before and after.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const tiles = (page: Page) => page.getByRole("list", { name: "Your figures" });
const figure = async (page: Page, label: string) => Number(await tiles(page).getByRole("link", { name: new RegExp(`^${label}`) }).locator("strong").textContent());

test("recruiter: tiles, a new lead counts, a tile opens its list, the skill box opens Find Candidates", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await expect(tiles(page).getByRole("listitem")).toHaveCount(14);
  const before = await figure(page, "New Recruiter Leads");

  await page.getByRole("navigation", { name: "Quick actions" }).getByRole("link", { name: "+ Add Company" }).click();
  await page.waitForURL("**/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(`E2E Rec032 ${Date.now()} Labs`);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);

  await page.goto("/recruiter/dashboard");
  expect(await figure(page, "New Recruiter Leads")).toBe(before + 1);

  await tiles(page).getByRole("link", { name: /^Follow-ups Due/ }).click(); // AC3
  await page.waitForURL("**/recruiter/follow-ups?due=today");
  await expect(page.getByRole("heading", { name: "Follow-ups", level: 2 })).toBeVisible();

  await page.goto("/recruiter/dashboard");
  const search = page.getByRole("search", { name: "Find candidates by skill" });
  await search.getByRole("button", { name: "Find candidates" }).click();
  await expect(search.getByRole("alert")).toHaveText("Type at least one skill.");
  await search.getByLabel("Skill").fill("Java");
  await search.getByRole("button", { name: "Find candidates" }).click();
  await page.waitForURL("**/recruiter/find-candidates?all=Java");
  await expect(page.getByRole("heading", { name: "Find Candidates" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("manager: the team's figures, narrowed to one recruiter; no scheduling actions", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await page.waitForURL("**/recruiter/dashboard");
  await expect(tiles(page).getByRole("listitem")).toHaveCount(14);
  const actions = page.getByRole("navigation", { name: "Quick actions" });
  await expect(actions.getByRole("link", { name: "+ Add Company" })).toBeVisible();
  await expect(actions.getByRole("link", { name: /Schedule/ })).toHaveCount(0);

  const select = page.getByRole("combobox", { name: "Recruiter" });
  const name = (await select.locator("option").nth(1).textContent())!;
  await select.selectOption({ label: name });
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForURL(/\/recruiter\/dashboard\?recruiter=[0-9a-f-]{36}$/);
  await expect(page.getByText(`${name}'s figures.`)).toBeVisible();
  await expect(tiles(page).getByRole("link", { name: /^Active Companies/ })).toHaveAttribute("href", /assigned=[0-9a-f-]{36}$/);

  await page.goto(`/recruiter/dashboard?recruiter=${"0".repeat(8)}-0000-0000-0000-${"0".repeat(12)}`);
  await expect(page.getByRole("status").filter({ hasText: "That recruiter is not in your team." })).toBeVisible();
});
