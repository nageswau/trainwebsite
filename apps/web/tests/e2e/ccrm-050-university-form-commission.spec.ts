import { expect, test, type Page } from "@playwright/test";

import { registerApprovedAgency } from "./helpers/agency";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-050 (DEC-SCOPE-320): the Overseas Admin enters the agent-Master commission on Add University (one save) and sees it prefilled on
// Edit; an agency Master reads it once the university is published. A partnership head never sees the fieldset and the API refuses the
// key (403). Requires the stack seeded with `python -m app.seed`. Unique names per run (shared E2E DB).

async function signIn(page: Page, portal: "overseas" | "admin", email: string, password: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

async function fillUniversity(page: Page, name: string) {
  await page.getByLabel("University name (required)").fill(name);
  const combo = page.getByRole("combobox", { name: "Country (required)" });
  await combo.fill("United Kingdom");
  await page.getByRole("option", { name: /United Kingdom/ }).first().click();
  await page.getByLabel("City (required)").fill("London");
  await page.getByLabel("Overview (shown in the public catalogue once published)").fill("An e2e overview.");
}

test("Overseas Admin adds a university with a 10% agent commission; Master sees it after publish (AC1, AC3)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const name = `CCRM050 University ${stamp}`;

  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123");
  await page.goto("/partnership/universities/new");
  const fieldset = page.getByRole("group", { name: "Agent Master commission" });
  await expect(fieldset).toBeVisible();
  await fillUniversity(page, name);
  await fieldset.getByLabel("Percent", { exact: true }).fill("10");
  await fieldset.getByLabel("Note").fill("Standard agent rate");
  const [created] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/v1/partnership/universities") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Add university" }).click(),
  ]);
  expect(created.status()).toBe(201);
  const uni = (await created.json()).university;
  expect(uni.agent_commission).toEqual({ percent: "10.00", amount: null, currency: null, note: "Standard agent rate" });
  await page.waitForURL(`**/partnership/universities/${uni.id}`);
  const card = page.locator("section[aria-labelledby=uni-agent-commission]");
  await expect(card).toContainText("10.00%");

  await page.goto(`/partnership/universities/${uni.id}/edit`);
  await expect(page.getByRole("group", { name: "Agent Master commission" }).getByLabel("Percent", { exact: true })).toHaveValue("10.00");

  expect((await page.request.post(`/api/v1/partnership/universities/${uni.id}/publish`)).status()).toBe(200);
  const masterPage = await (await browser.newContext()).newPage();
  const masterEmail = await registerApprovedAgency(masterPage, stamp, "ccrm050");
  await signIn(masterPage, "overseas", masterEmail, "Sup3r-Secret-Pass!");
  const detail = await masterPage.request.get(`/api/v1/workflows/overseas/agent/crm/partner-universities/${uni.id}`);
  expect((await detail.json()).university.agent_commission.percent).toBe("10.00");
});

test("a partnership head never sees the fieldset and the API refuses the key (AC2); the form fits a phone", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const head = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_head", division: "global", full_name: `CCRM050 Head ${stamp}`, email: `ccrm050-h-${stamp}@example.local` },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, head.development_welcome_token);

  await signIn(page, "admin", head.email, E2E_PASSWORD);
  await page.goto("/partnership/universities/new");
  await expect(page.getByLabel("University name (required)")).toBeVisible();
  await expect(page.getByRole("group", { name: "Agent Master commission" })).toHaveCount(0);
  await expect(page.getByLabel("Percent", { exact: true })).toHaveCount(0);

  const country = (await (await page.request.get("/api/v1/lookups/countries?q=United Kingdom")).json()).items[0].id;
  const refused = await page.request.post("/api/v1/partnership/universities", {
    data: { name: `CCRM050 Refused ${stamp}`, country_id: country, city: "London", agent_commission: { percent: "10" } },
  });
  expect(refused.status()).toBe(403);
  expect(await refused.text()).toContain("Only a super admin or an overseas admin can change the agent commission");

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
