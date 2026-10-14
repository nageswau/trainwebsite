import { expect, test, type Page } from "@playwright/test";

// mgmt-026 (EVID-017 §25/§26, spec PN1-PN16): a partner opens Next month plan & targets from the Command Center, plans a month, adds a
// KPI item (New agents, target 30) and a free-text item, ticks the free-text item done (AC3) and sees the KPI item in Target vs actual.
// Plans are unique per month in the shared database, so the test plans the latest unplanned month in the window, or -- when every
// month is planned -- reuses the latest plan (reopened). Its items carry a unique stamp, so it only ever checks its own rows.

const PASSWORD = "Demo@123";

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("signed out, /management/plans sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/plans");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fplans$/);
});

test("a partner plans a month, adds a KPI item and a free-text item, ticks it done and sees target vs actual", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const kpiText = `Recruit 30 new agents e2e-${stamp}`;
  const freeText = `Sign Korean universities e2e-${stamp}`;

  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Next month plan & targets" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Next month plan & targets" })).toBeVisible();

  const month = page.getByLabel("Month", { exact: true });
  let key: string;
  if (await month.count()) {
    key = (await month.locator("option").last().getAttribute("value")) as string;
    await month.selectOption(key);
    await page.getByRole("button", { name: "Plan this month" }).click();
    await expect(page).toHaveURL(new RegExp(`/management/plans/${key}$`));
  } else {
    const { max_month } = await (await page.request.get("/api/v1/management/plans/options")).json();
    key = max_month;
    await page.request.patch(`/api/v1/management/plans/${key}`, { data: { status: "active" } });
    await page.goto(`/management/plans/${key}`);
  }
  await expect(page.getByRole("heading", { level: 2, name: /^Plan for / })).toBeVisible();

  const add = page.getByRole("form", { name: "Add item" });
  await add.getByLabel("Vertical", { exact: true }).selectOption("abroad");
  await add.getByLabel("KPI", { exact: true }).selectOption("agents");
  await add.getByLabel("Target", { exact: true }).fill("30");
  await add.getByLabel("Item", { exact: true }).fill(kpiText);
  await add.getByRole("button", { name: "Add item" }).click();
  const progress = page.getByRole("region", { name: "Target vs actual", exact: true });
  const row = progress.getByRole("row").filter({ hasText: kpiText });
  await expect(row).toBeVisible();
  await expect(row.getByRole("rowheader")).toHaveText("Abroad Education");
  await expect(row.getByRole("cell").nth(1)).toHaveText("New agents");
  await expect(row.getByRole("cell").nth(2)).toHaveText("30");
  await expect(row.getByRole("cell").nth(4)).toHaveText(/^\d+%$/);

  await expect(add.getByLabel("Item", { exact: true })).toHaveValue(""); // ready for the next item
  await add.getByLabel("Item", { exact: true }).fill(freeText);
  await add.getByRole("button", { name: "Add item" }).click();
  const done = page.getByRole("checkbox", { name: `Done: ${freeText}` });
  await expect(done).not.toBeChecked();
  await done.check();
  await expect(page.getByRole("status")).toHaveText(`"${freeText}" marked done.`);
  await expect(done).toBeChecked();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: `Done: ${freeText}` })).toBeChecked();
  await expect(page.getByText(/^Other plan items: \d+ of \d+ done\.$/)).toBeVisible();
});
