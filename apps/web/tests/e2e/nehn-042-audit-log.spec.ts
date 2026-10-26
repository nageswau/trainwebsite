import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// nehn-042 (DEC-SCOPE-288): the admin Audit log -- filters, one entity's whole history, the division scope, paging links, phone layout.
// The fixture is an inactive (never public) IT program the IT Admin creates and then edits, so its history is exactly two rows.

const PASSWORD = "Demo@123";

async function apiLogin(request: APIRequestContext, email: string, division: string) {
  const response = await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD, division } });
  expect(response.ok()).toBeTruthy();
}

async function inactiveProgram(request: APIRequestContext): Promise<string> {
  const slug = `n042-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const created = await request.post("/api/v1/admin/programs", { data: { slug, category: "QA", title: `Audit QA ${slug}`, active: false } });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  expect((await request.patch(`/api/v1/admin/programs/${id}`, { data: { summary: "edited for nehn-042" } })).ok()).toBeTruthy();
  return id;
}

const rows = (page: Page) => page.getByRole("table", { name: "Audit log" }).locator("tbody tr");

test("IT Admin finds one record's whole history from the nav, and the filters survive a refresh (AC1)", async ({ page }) => {
  await apiLogin(page.request, "itadmin@edusphere.local", "it");
  const id = await inactiveProgram(page.request);
  await page.goto("/it/admin/dashboard");
  await page.getByRole("link", { name: "Audit Log", exact: true }).first().click();
  await expect(page).toHaveURL(/\/it\/admin\/audit-log$/);
  await expect(page.getByRole("heading", { name: "Audit Log" })).toBeVisible();
  await expect(page.getByLabel("Division")).toHaveCount(0);

  await page.getByLabel("Entity type").fill("program");
  await page.getByLabel("Entity reference").fill(id);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(new RegExp(`entity_id=${id}`));
  await expect(rows(page)).toHaveCount(2);
  await expect(rows(page).nth(0)).toContainText("program.update");
  await expect(rows(page).nth(1)).toContainText("program.create");
  await expect(rows(page).nth(0)).toContainText("IT Division Administrator");

  await page.reload();
  await expect(page.getByLabel("Entity reference")).toHaveValue(id);
  await expect(rows(page)).toHaveCount(2);

  // The actor link lists everything that person did; the entity link goes back to the one record.
  await rows(page).nth(0).getByRole("link", { name: "IT Division Administrator" }).click();
  await expect(page).toHaveURL(/\?actor=[0-9a-f-]{36}$/);
  await expect(rows(page).first()).toBeVisible();
  await page.goBack();
  await rows(page).nth(1).getByRole("link", { name: id }).click();
  await expect(rows(page)).toHaveCount(2);

  await page.getByRole("link", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/it\/admin\/audit-log$/);
  await expect(page.getByLabel("Entity reference")).toHaveValue("");
});

test("Overseas Admin never sees the IT Admin's rows; Super Admin does, by division (AC2)", async ({ page, browser }) => {
  await apiLogin(page.request, "itadmin@edusphere.local", "it");
  const id = await inactiveProgram(page.request);

  const overseas = await browser.newContext();
  const overseasPage = await overseas.newPage();
  await apiLogin(overseasPage.request, "overseasadmin@edusphere.local", "overseas");
  await overseasPage.goto(`/overseas/admin/audit-log?entity_type=program&entity_id=${id}`);
  await expect(overseasPage.getByRole("status")).toHaveText("No audit records match these filters.");
  await overseas.close();

  const sup = await browser.newContext();
  const superPage = await sup.newPage();
  await apiLogin(superPage.request, "superadmin@edusphere.local", "global");
  await superPage.goto(`/admin/security-logs?entity_type=program&entity_id=${id}&division=overseas`);
  await expect(superPage.getByRole("status")).toHaveText("No audit records match these filters.");
  await superPage.getByLabel("Division").selectOption("it");
  await superPage.getByRole("button", { name: "Apply" }).click();
  await expect(rows(superPage)).toHaveCount(2);
  await expect(superPage.getByRole("heading", { name: "Export audit log" })).toBeVisible(); // ADM-014 export unchanged
  await sup.close();
});

test("a mistyped actor is explained and the form keeps it; paging links appear past one page (AC3)", async ({ page }) => {
  await apiLogin(page.request, "superadmin@edusphere.local", "global");
  await page.goto("/admin/security-logs?actor=Asha");
  await expect(page.locator(".form-error")).toContainText("user reference");
  await expect(page.getByLabel("Done by")).toHaveValue("Asha");

  // 26 programs give 52 program.* rows, so there is always a second page.
  test.setTimeout(60_000);
  await apiLogin(page.request, "itadmin@edusphere.local", "it");
  for (let i = 0; i < 26; i += 1) await inactiveProgram(page.request);
  await apiLogin(page.request, "superadmin@edusphere.local", "global");
  await page.goto("/admin/security-logs?action=program.&division=it");
  await expect(rows(page)).toHaveCount(50);
  await expect(page.getByRole("link", { name: "Previous page" })).toHaveCount(0);
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page).toHaveURL(/action=program\.&division=it&offset=50/);
  await expect(page.getByText(/^Showing 51–/)).toBeVisible();
  await page.getByRole("link", { name: "Previous page" }).click();
  await expect(page).toHaveURL(/action=program\.&division=it$/);
});

test("other roles are refused, in the page and at the API", async ({ page }) => {
  await apiLogin(page.request, "counselor@edusphere.local", "overseas");
  await page.goto("/overseas/admin/audit-log");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  expect((await page.request.get("/api/v1/admin/audit")).status()).toBe(403);
});

for (const [name, width] of [["phone", 375], ["tablet", 768], ["desktop", 1280]] as const) {
  test(`the audit log fits a ${name} without sideways scrolling`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await apiLogin(page.request, "itadmin@edusphere.local", "it");
    await inactiveProgram(page.request);
    await page.goto("/it/admin/audit-log?entity_type=program");
    await expect(rows(page).first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
