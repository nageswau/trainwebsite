import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-005 (AC1-AC5): a partnership head imports a CSV from the University Master list and sees the per-row report (created, duplicate of
// the master, invalid) and the history; uploading the same file again adds nothing; a partnership manager has no import. Throwaway
// accounts via the admin API.

async function superAdmin(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "overseas" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function accounts(page: Page, stamp: number) {
  await superAdmin(page);
  const head = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc005-h-${stamp}@example.local` },
  })).json();
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc005-m-${stamp}@example.local`,
            partnership_profile: { employee_id: `U5-${stamp}`, reporting_head_user_id: head.id } },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, head.development_welcome_token);
  await activateWithToken(page.request, manager.development_welcome_token);
  return { head, manager };
}

async function upload(page: Page, csv: string) {
  await page.getByLabel("Filled-in universities file").setInputFiles({ name: "universities.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Import universities" }).click();
  await expect(page.getByRole("heading", { name: "Import result" })).toBeVisible();
}

test("head imports a file with a per-row report; the same file again adds nothing; a manager cannot import", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const { head, manager } = await accounts(page, stamp);
  await signIn(page, "admin", head.email, "/partnership/head/team");
  const uk = (await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json()).items.find((c: { label: string }) => c.label === "United Kingdom").id;
  const existing = (await (await page.request.post("/api/v1/partnership/universities", { data: { name: `E2E Existing ${stamp}`, country_id: uk, city: "Leeds" } })).json()).university;

  await page.goto("/partnership/universities");
  await page.getByRole("link", { name: "Import universities" }).click();
  await page.waitForURL("**/partnership/universities/import");
  await expect(page.getByRole("link", { name: /Download the template/ })).toBeVisible();
  const csv = [
    "name,country,city,institution_type,priority",
    `E2E Import ${stamp} One,GB,London,University,A`,
    `E2E Import ${stamp} Two,United Kingdom,Bath,college,`,
    `E2E Import ${stamp} Three,JP,Tokyo,Language School,b`,
    `e2e existing ${stamp},GB,Leeds,university,`,
    `E2E Import ${stamp} Bad,Atlantis,Nowhere,university,`,
  ].join("\n");

  // AC1: an accurate per-row report
  await upload(page, csv);
  await expect(page.getByText("3 created, 1 duplicate, 1 invalid.", { exact: false })).toBeVisible();
  const skipped = page.getByRole("table", { name: "Rows not created" });
  await expect(skipped.getByRole("row")).toHaveCount(3);
  await expect(skipped).toContainText(`Already in the University Master: ${existing.university_code}`);
  await expect(skipped).toContainText("Unknown country: Atlantis");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /Download the full report/ }).click();
  const report = await (await download).path();
  expect(report).toBeTruthy();
  await expect(page.getByRole("cell", { name: head.full_name }).first()).toBeVisible(); // the history

  const created = await (await page.request.get(`/api/v1/partnership/universities?q=${encodeURIComponent(`E2E Import ${stamp}`)}&visibility=internal`)).json();
  expect(created.total).toBe(3);
  expect(created.items.every((u: { primary_manager: unknown; catalogue_visible: boolean }) => u.primary_manager === null && !u.catalogue_visible)).toBe(true);

  // AC2: the same file again creates nothing new
  await upload(page, csv);
  await expect(page.getByText(/No universities were added \(0 created, 4 duplicates, 1 invalid\)/)).toBeVisible();
  expect((await (await page.request.get(`/api/v1/partnership/universities?q=${encodeURIComponent(`E2E Import ${stamp}`)}`)).json()).total).toBe(3);

  // IM8: a partnership manager has no import
  await signIn(page, "overseas", manager.email, "/partnership/dashboard");
  await page.goto("/partnership/universities");
  await expect(page.getByRole("heading", { name: "Universities and institutions" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Import universities" })).toHaveCount(0);
  await page.goto("/partnership/universities/import");
  await expect(page.getByText("Your role cannot import universities.")).toBeVisible();
  expect((await page.request.get("/api/v1/partnership/universities/imports/template")).status()).toBe(403);
});
