import { expect, test, type Page } from "@playwright/test";

// pob-016 (DEC-SCOPE-419): the seeded Team Lead switches the company's rule on; the recruiter marks an item missing and sees its follow-up (AC1), is refused sourcing with the
// missing items listed (AC2), then the Team Lead overrides with a reason, which shows in the History (AC3), and the recruiter starts sourcing. On a phone nothing scrolls sideways.
const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(email === MANAGER ? "/admin/login" : "/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(/\/(recruiter|admin)\//);
}

test("the checklist blocks sourcing until a Team Lead overrides it", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  await signIn(page, RECRUITER);
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { company } = await post("/api/v1/recruiter/companies", { name: `E2E Pob016 ${stamp} Pvt` });
  await post(`/api/v1/recruiter/companies/${company.id}/contacts`, { name: `Dev Decider ${stamp}`, mobile: `9${String(stamp).slice(-9)}`, is_primary: true });
  const { requirement } = await post("/api/v1/recruiter/requirements", { company_id: company.id, title: `Pob016 ${stamp}`, location: "Pune" });
  await post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { status: "requirement_received" });
  const path = `/recruiter/requirements/${requirement.id}`;
  const card = page.getByRole("region", { name: "Validation checklist" });

  await signIn(page, MANAGER);
  await page.goto(path);
  await card.getByLabel("Rule for this company").selectOption("block");
  await expect(card.getByText("This company's rule is saved.")).toBeVisible();
  await expect(card.getByText("Sourcing cannot start until this is complete.")).toBeVisible();
  await expect(card.getByRole("radio")).toHaveCount(0); // a Team Lead does not answer items

  await signIn(page, RECRUITER);
  await page.goto(path);
  const budget = card.getByRole("group", { name: "Salary budget" });
  await budget.getByRole("radio", { name: "Missing" }).check();
  await expect(card.getByText("Salary budget: Missing. A follow-up was added.")).toBeVisible();
  await expect(budget.getByText(`Follow-up with Dev Decider ${stamp} due`)).toBeVisible();

  const status = page.getByRole("region", { name: "Change status" });
  await status.getByLabel("New status").selectOption("sourcing");
  await status.getByRole("button", { name: "Change status" }).click();
  await expect(status.getByRole("alert")).toContainText("Still needed:");
  await expect(status.getByRole("alert")).toContainText("Salary budget");
  await expect(page.locator(".badge").first()).toHaveText("Requirement Received");

  await page.goto(`/recruiter/companies/${company.id}`);
  await expect(page.getByText("Clarification from the client").first()).toBeVisible();

  await signIn(page, MANAGER);
  await page.goto(path);
  await card.getByLabel("Reason for the override").fill("Client is away; start sourcing now");
  await card.getByRole("button", { name: "Override the checklist" }).click();
  await expect(card.getByText("Checklist overridden.")).toBeVisible();
  await expect(card.getByText(/Client is away; start sourcing now/)).toBeVisible();
  await expect(page.getByText("Checklist overridden", { exact: true }).first()).toBeVisible(); // the History

  await signIn(page, RECRUITER);
  await page.goto(path);
  await status.getByLabel("New status").selectOption("sourcing");
  await status.getByRole("button", { name: "Change status" }).click();
  await expect(page.getByText("Status changed to Sourcing.")).toBeVisible();
  await expect(card.getByText(/already started/)).toBeVisible();

  await page.setViewportSize({ width: 375, height: 812 });
  await card.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
