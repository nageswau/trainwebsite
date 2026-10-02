import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-012 (DEC-SCOPE-055) -- a Master starts a visa case from an offer, the date-order error lands on the interview field, a skip is
// confirmed, the decision is recorded once and the case turns read-only; 320 px. Unique names per run (shared E2E DB); the set-up is
// agn-013-enrollment.spec.ts's.
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function applicationAtOffer(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();

  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — no login$`));
  await page.locator("#agent-app-university").selectOption(universities.find((u: { slug: string }) => u.slug === "university-of-manchester").id);
  await page.getByLabel("Intake (required)").fill("Sep 2027");
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Application created." })).toBeVisible();

  await page.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  const detail = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await detail.getByLabel("Move to").selectOption("offer");
  await detail.getByRole("button", { name: "Update status" }).click();
  await expect(detail.getByRole("status")).toHaveText("Status updated to Offer.");
  return detail;
}

test("a Master runs a visa case from an offer to a recorded decision (AC1-AC5, AC11)", async ({ page }) => {
  const name = `E2E Visa ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const detail = await applicationAtOffer(page, name);
  const visa = detail.getByRole("region", { name: "Visa" });
  await visa.getByRole("button", { name: "Start visa case" }).click();
  await visa.getByLabel("Visa application date (optional)").fill("2027-05-01");
  await visa.getByRole("form", { name: "Start visa case" }).getByRole("button", { name: "Start visa case" }).click();
  await expect(detail.getByText("Visa case started.")).toBeVisible();
  await visa.getByRole("button", { name: "Edit visa details" }).click();
  await visa.getByLabel("Interview date (optional)").fill("2027-04-01");
  await visa.getByRole("button", { name: "Save visa details" }).click();
  await expect(visa.getByText("The interview date cannot be before the visa application date")).toBeVisible();
  await visa.getByLabel("Interview date (optional)").fill("2027-05-20");
  await visa.getByRole("button", { name: "Save visa details" }).click();
  await expect(visa.getByText("2027-05-20")).toBeVisible();
  await visa.getByRole("button", { name: "Move visa stage" }).click();
  await visa.getByLabel("Move to").selectOption("decision");
  await visa.getByRole("button", { name: "Move", exact: true }).click();
  await visa.getByRole("button", { name: "Yes, move" }).click();
  await visa.getByRole("button", { name: "Record decision" }).click();
  await visa.getByRole("radio", { name: "Approved" }).check();
  await visa.getByRole("button", { name: "Record decision" }).click();
  await visa.getByRole("button", { name: "Yes, record decision" }).click();
  await expect(detail.getByText("Visa decision recorded.")).toBeVisible();
  await expect(visa.getByRole("button")).toHaveCount(0);
});

test("the visa section fits a 320 px screen (AC11)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const detail = await applicationAtOffer(page, `E2E Visa320 ${stamp()}`);
  await detail.getByRole("region", { name: "Visa" }).getByRole("button", { name: "Start visa case" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
