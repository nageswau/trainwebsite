import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-014 (AC1-AC4, P1): a partnership manager drafts an exclusive MoU for India from the university page, sends it for review; the head
// approves it; the manager uploads the MoU, records both signatories and signs it -- the university moves to Agreement Signed and the
// MoU shows as Expiring (30 days left); the manager activates and renews it (the renewal links back). The MoU & Agreements menu lists
// both; an overseas_admin sees no agreements; the pages fit a phone. Throwaway accounts via the real admin API.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc014-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc014-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U14-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc014-a-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Agreements University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, admin, university };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("an MoU is drafted, approved by the head, signed, activated and renewed", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const { head, manager, admin, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Agreements", exact: true }) });
  const status = section.locator("p[role=status]");

  // AC1 + P1: the owning manager drafts an exclusive MoU for India (30 days left on it, so it will read Expiring once signed).
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await expect(section.getByText("No agreements recorded yet.")).toBeVisible();
  await section.getByRole("button", { name: "New agreement" }).click();
  await section.getByRole("button", { name: "Create draft" }).click();
  await expect(section.locator(".form-error[role=alert]")).toHaveText("Choose the agreement type.");
  await section.getByLabel("Agreement type (required)").selectOption("mou");
  await section.getByLabel("Exclusivity (required)").selectOption("exclusive");
  await section.getByLabel("Start date (required)").fill(day(-700));
  await section.getByLabel("Expiry date (required)").fill(day(30));
  await section.getByLabel("Territory").fill("India (all states)");
  await section.getByLabel("Commercial terms (summary)").fill("Recruitment partnership for Indian students");
  await section.getByLabel("All courses of this university").check();
  await section.getByRole("combobox", { name: "Add a country" }).fill("India");
  await section.getByRole("option", { name: /^India/ }).first().click();
  await expect(section.getByRole("list", { name: "Countries covered" })).toContainText("India");
  await section.getByRole("button", { name: "Create draft" }).click();
  await expect(status).toHaveText(/^Agreement MOU-\d{6} created as a draft\.$/);
  const mou = (await status.textContent())!.match(/MOU-\d{6}/)![0];
  const card = section.locator("li.card", { hasText: mou });
  await expect(card.getByText("Draft", { exact: true })).toBeVisible();

  for (const label of ["Sent", "Under Review"]) {
    await card.getByRole("button", { name: `Move to ${label} (${mou})` }).click();
    await card.getByRole("button", { name: `Move to ${label}`, exact: true }).click();
    await expect(status).toHaveText(`${mou} moved to ${label}.`);
  }
  await expect(card.getByRole("button", { name: /Move to Approved/ })).toHaveCount(0); // AG6: the head approves

  // The head approves.
  await signIn(page, "/admin/login", head.email);
  await page.goto(universityPage);
  await card.getByRole("button", { name: `Move to Approved (${mou})` }).click();
  await card.getByLabel("Note (optional)").fill("Terms checked");
  await card.getByRole("button", { name: "Move to Approved", exact: true }).click();
  await expect(status).toHaveText(`${mou} moved to Approved.`);

  // AC2: signing needs the document and both signatories.
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await card.getByRole("button", { name: `Move to Signed (${mou})` }).click();
  await card.getByRole("button", { name: "Move to Signed", exact: true }).click();
  await expect(section.locator(".form-error[role=alert]")).toContainText("before signing");
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Kind (required)").selectOption("mou");
  await page.getByLabel("Title (required)").fill("Signed MoU 2026");
  await page.getByLabel("File (required)").setInputFiles({ name: "mou.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByRole("link", { name: "Download Signed MoU 2026" })).toBeVisible();
  await card.getByRole("button", { name: `Edit ${mou}` }).click();
  await expect(card.getByLabel("Territory")).toHaveCount(0); // AG11: the terms are frozen once approved
  await card.getByLabel("Agreement document").selectOption({ label: "Signed MoU 2026 (version 1)" });
  await card.getByRole("combobox", { name: "Signed by EduSphere" }).fill(manager.email);
  await card.getByRole("option", { name: new RegExp(`E2E Manager ${stamp}`) }).click();
  await card.getByLabel("EduSphere signed on").fill(day(-1));
  await card.getByLabel("Signed by the university (name)").fill("Prof. A. Registrar");
  await card.getByLabel("University signed on").fill(day(-2));
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect(status).toHaveText("Agreement updated.");
  await card.getByRole("button", { name: `Move to Signed (${mou})` }).click();
  await card.getByRole("button", { name: "Move to Signed", exact: true }).click();
  await expect(status).toHaveText(`${mou} moved to Signed.`);
  // AC3 + the stage: Expiring is derived; the university is at Agreement Signed.
  await expect(card.getByText("Expiring", { exact: true })).toBeVisible();
  await expect(card.getByText(/^Expires in (29|30) days$/)).toBeVisible(); // the API counts in IST, `day` in UTC
  await expect(page.getByText("Agreement Signed").first()).toBeVisible();
  await card.getByText("Agreement details").click();
  await expect(card.getByText(`E2E Manager ${stamp}, `)).toBeVisible();
  await expect(card.getByRole("link", { name: "Signed MoU 2026 (version 1)" })).toBeVisible();

  await card.getByRole("button", { name: `Move to Active (${mou})` }).click();
  await card.getByRole("button", { name: "Move to Active", exact: true }).click();
  await expect(status).toHaveText(`${mou} moved to Active.`);

  // AC4: the renewal is a new draft linked to this MoU.
  await card.getByRole("button", { name: `Renew ${mou}` }).click();
  await expect(card.getByLabel("New start date")).toHaveValue(day(31));
  await card.getByRole("button", { name: "Start renewal" }).click();
  await expect(status).toHaveText(`Renewal of ${mou} started as a draft.`);
  await expect(section.getByText(new RegExp(`^Renewal of ${mou}`))).toBeVisible();
  await expect(card.getByText(/^Renewed by MOU-\d{6}/)).toBeVisible();

  // The MoU & Agreements menu lists both, filters to Expiring, and fits a phone.
  await page.getByRole("link", { name: "MoU & Agreements" }).first().click();
  await expect(page.getByRole("heading", { name: "University agreements" })).toBeVisible();
  await page.goto(`/partnership/agreements?q=${stamp}`);
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await page.goto(`/partnership/agreements?q=${stamp}&status=expiring`);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(0);
  await page.goto(universityPage);
  expect(await noSideScroll(page)).toBe(0);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AG13: an overseas_admin reads the university but never its agreements.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(page.getByRole("heading", { name: university.name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Agreements", exact: true })).toHaveCount(0);
  await page.goto("/partnership/agreements");
  await expect(page.getByText("University agreements access required")).toBeVisible();
});
