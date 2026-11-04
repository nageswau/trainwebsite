import { expect, test, type Browser, type Page } from "@playwright/test";

// hrc-007 (DEC-SCOPE-380): an employer's published posting waits for approval (A4/A6, AC1); the HR Manager approves it from the
// Approvals queue and it becomes visible (AC2, the + scenario); a rejection needs a reason and returns it to draft (AC3); a role without
// `jobs.approve` gets the access card. Throwaway employers per test; seeded demo staff accounts.
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function postAndPublish(page: Page, title: string) {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const registered = await page.request.post("/api/v1/employer/register", {
    data: { email: `hrc007-${unique}@example.local`, password: "Sup3r-Secret-Pass!", full_name: "HRC7 Employer", company_name: `HRC7 Co ${unique}` },
  });
  expect(registered.ok()).toBeTruthy();
  await page.goto("/it/employer/dashboard");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await card.getByLabel("Title").fill(title);
  await card.getByRole("button", { name: "Post job" }).click();
  await expect(card.getByText("Job posted.")).toBeVisible();
  const posting = card.locator(".card", { hasText: title });
  await posting.getByRole("button", { name: "Publish" }).click();
  await expect(posting.getByText("Sent for approval. Students see it once it is approved.")).toBeVisible();
  await expect(posting.getByText("Awaiting approval")).toBeVisible();
  await expect(posting.getByText("Pending Approval")).toBeVisible();
  await expect(posting.getByRole("button", { name: "Publish" })).toHaveCount(0);
  return posting;
}

async function approverPage(browser: Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, "hr.manager@edusphere.local");
  await page.getByRole("link", { name: "Approvals" }).click();
  await expect(page.getByRole("heading", { name: "Vacancy approvals" })).toBeVisible();
  return page;
}

test("an employer's posting waits for the HR Manager, who approves it, and then students see it", async ({ page, browser }) => {
  const title = `HRC7 Approve ${Date.now()}`;
  await postAndPublish(page, title);
  const hr = await approverPage(browser);
  const item = hr.getByRole("listitem").filter({ hasText: title });
  await expect(item.getByText("Employer", { exact: true })).toBeVisible();
  await expect(item.getByText(/Sent for approval by HRC7 Employer/)).toBeVisible();
  await item.getByLabel("Note, or the reason when rejecting").fill("Checked with the client");
  await item.getByRole("button", { name: "Approve" }).click();
  await expect(hr.getByText(/approved\. It is now open\./)).toBeVisible();
  await expect(hr.getByRole("listitem").filter({ hasText: title })).toHaveCount(0);
  await hr.context().close();

  await page.reload();
  await expect(page.locator(".card", { hasText: title }).getByText("Visible to students")).toBeVisible();
});

test("a rejection needs a reason and sends the posting back to draft", async ({ page, browser }) => {
  const title = `HRC7 Reject ${Date.now()}`;
  await postAndPublish(page, title);
  const hr = await approverPage(browser);
  const item = hr.getByRole("listitem").filter({ hasText: title });
  await item.getByRole("button", { name: "Reject" }).click();
  await expect(item.getByRole("alert")).toHaveText("Give a reason to reject this requirement.");
  await expect(item.getByLabel("Note, or the reason when rejecting")).toBeFocused();
  await item.getByLabel("Note, or the reason when rejecting").fill("Add the salary range");
  await item.getByRole("button", { name: "Reject" }).click();
  await expect(hr.getByText(/rejected and returned to draft\./)).toBeVisible();
  await hr.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(hr)).toBe(true);
  await hr.context().close();

  await page.reload();
  const posting = page.locator(".card", { hasText: title });
  await expect(posting.getByText("Draft", { exact: true })).toBeVisible();
  await expect(posting.getByRole("button", { name: "Publish" })).toBeVisible();
});

test("a role without the approve grant gets the access card, not the queue", async ({ page }) => {
  await signIn(page, "placement.officer@edusphere.local");
  await page.goto("/it/hr-manager/approvals");
  await expect(page.getByRole("heading", { name: "Vacancy approvals" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/recruiter/requirement-approvals")).status()).toBe(403);
});
