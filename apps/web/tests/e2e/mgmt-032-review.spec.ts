import { expect, test, type Page } from "@playwright/test";

// mgmt-032 (spec MR1-MR14): a partner opens the Monthly business review, drafts a month, writes the Problems and Next-month answers,
// finalises it (after a confirmation) and downloads the PDF; finalising without the Problems answers is refused on the page. The super
// admin and the accountant get the access card. The shared test DB keeps every review, so each run drafts a random month long past
// (a final one answers 409 and another is tried) rather than relying on the last few months being free.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function draftAMonth(page: Page): Promise<string> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const month = `${2001 + Math.floor(Math.random() * 20)}-${String(1 + Math.floor(Math.random() * 12)).padStart(2, "0")}`;
    const response = await page.request.post(`/api/v1/management/reviews/${month}/generate`);
    if (response.status() === 201 || (response.status() === 200 && (await response.json()).status === "draft")) return month;
  }
  throw new Error("No free month to draft");
}

test("a partner drafts, answers, finalises and downloads a month's review", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Monthly business review" }).first().click();
  await page.waitForURL(/\/management\/reviews$/);
  await expect(page.getByRole("form", { name: "Generate a review" })).toBeVisible();

  const month = await draftAMonth(page);
  await page.goto(`/management/reviews/${month}`);
  await expect(page.getByRole("heading", { level: 2, name: /^EduSphere Monthly Business Review — / })).toBeVisible();
  for (const section of ["1. Revenue", "2. Expenses", "3. Profitability", "4. Sales", "5. Partnerships", "6. People", "7. Marketing", "8. Investments", "9. Problems", "10. Next month"]) {
    await expect(page.getByRole("region", { name: section, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "6. People" }).getByText("Not tracked")).toBeVisible();

  await page.getByLabel("What went wrong?").fill("Two agents churned.");
  await page.getByRole("button", { name: "Finalise review" }).click();
  await expect(page.locator(".form-error")).toHaveText("Answer every Problems question before finalising: What is delayed?, What needs management intervention?");

  await page.getByLabel("What is delayed?").fill("The Pune office fit-out.");
  await page.getByLabel("What needs management intervention?").fill("Approve the hiring plan.");
  await page.getByLabel("Hiring").fill("Two trainers.");
  await page.getByRole("button", { name: "Save answers" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Answers saved." })).toBeVisible();

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Finalise review" }).click();
  await expect(page.getByText("Review finalised. Partners have been sent a link.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save answers" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Final", { exact: true })).toBeVisible();
  await expect(page.getByText("Two trainers.")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toBe(`monthly-review-${month}.pdf`);
});

test("the super admin and the accountant get the access card", async ({ page }) => {
  for (const email of ["superadmin@edusphere.local", "accountant@edusphere.local"]) {
    await page.context().clearCookies();
    await signIn(page, email);
    await page.goto("/management/reviews");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByRole("main").getByText("₹")).toHaveCount(0);
  }
});
