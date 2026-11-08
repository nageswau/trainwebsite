import { expect, test, type Page } from "@playwright/test";

// pob-026 (DEC-SCOPE-435): a manual close of a requirement needs a reason (S11), and the no-login survey page explains an unknown link
// without a session, on a phone too (S12). The answered/410 path needs a sweep-sent link: test_pob_026_surveys covers it, and the
// feature's browser QA drove it end to end.
const RECRUITER = "placement@edusphere.local";

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("closing a requirement by hand asks for a reason", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, RECRUITER);
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { company } = await post("/api/v1/recruiter/companies", { name: `E2E Pob026 ${stamp} Pvt` });
  const { requirement } = await post("/api/v1/recruiter/requirements", { company_id: company.id, title: `Pob026 ${stamp}`, location: "Pune" });
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const change = page.getByRole("region", { name: "Change status" });
  await change.getByLabel("New status").selectOption({ label: "Closed" });
  await expect(change.getByLabel("Reason for closing")).toBeVisible();
  await change.getByRole("button", { name: "Change status" }).click();
  await expect(change.getByText("Enter a reason for closing")).toBeVisible();
  await change.getByLabel("Reason for closing").fill("Client paused hiring");
  await change.getByRole("button", { name: "Change status" }).click();
  await expect(page.getByText("Status changed to Closed.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Status history" }).getByText(/Closed — Client paused hiring/)).toBeVisible();
});

test("an unknown survey link is explained without a session, on a phone too", async ({ page }) => {
  await page.context().setExtraHTTPHeaders({ "X-Forwarded-For": `10.26.${Date.now() % 250}.${Math.floor(Math.random() * 250) + 1}` });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/feedback/not-a-real-link");
  await expect(page).toHaveURL(/\/feedback\/not-a-real-link$/); // public: no redirect to a sign-in page
  await expect(page.getByRole("heading", { name: "Feedback link closed" })).toBeVisible();
  await expect(page.getByText(/This feedback link is not valid/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
