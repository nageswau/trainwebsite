import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickByValue, pickFromList } from "./helpers/pick";

// AGN-023 -- the Overseas Admin filters to agency applications with no counsellor and assigns one; the counsellor is not offered
// Enrolled and advances; the agency sees the counsellor's name. Unique names per run (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function agencyApplication(page: Page, name: string) {
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
}

test("admin assigns a counsellor to an agency application; counsellor advances (no Enrolled); agency sees the name", async ({ browser }) => {
  test.setTimeout(60_000); // three sign-ins, an application, a table search, a type-ahead search and three page checks: 15-17 s on a fresh stack
  const name = `E2E Handoff ${stamp()}`;
  const agency = await browser.newPage();
  await signIn(agency, "agent@edusphere.local", "Demo@123");
  await agencyApplication(agency, name);

  // The seeded counsellor is the one who signs in below, so assign that account by its name.
  const counselor = await browser.newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  const me = await (await counselor.request.get("/api/v1/auth/me")).json();
  const counselorName: string = me.full_name;
  const counselorId: string = me.id;

  const admin = await browser.newPage();
  await signIn(admin, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await admin.goto("/overseas/admin/applications?agency=any&counselor=none");
  await expect(admin.getByLabel("Agency", { exact: true })).toHaveValue("any");
  await expect(admin.getByLabel("Counsellor", { exact: true })).toHaveValue("none");
  await expect(admin.getByLabel("Agency", { exact: true }).locator("option:checked")).toHaveText("Any agency");
  await expect(admin.getByLabel("Counsellor", { exact: true }).locator("option:checked")).toHaveText("Not assigned");
  // The shared E2E database holds many rows and DataTable pages them, so narrow with the table's own search first.
  await admin.getByLabel("Search records").fill(name);
  const row = admin.getByRole("row", { name: new RegExp(name) });
  await row.getByRole("button", { name: "Assign counsellor" }).click();
  // Type-ahead: search by the counsellor's name (the shared DB holds ~1800 counsellors), then choose the option carrying their id
  // (names can collide, so never the first match by text).
  await pickByValue(row.getByRole("combobox", { name: "EduSphere counsellor" }), counselorId, counselorName);
  await row.getByRole("button", { name: "Save" }).click();
  await expect(admin.getByText(`${counselorName} assigned.`)).toBeVisible();

  await counselor.goto("/overseas/counselor/applications");
  const card = counselor.locator(".card").filter({ has: counselor.getByRole("heading", { name }) });
  await expect(card.getByText("Enrollment is confirmed by the agency.")).toBeVisible();
  await card.getByRole("button", { name: "Advance stage" }).click();
  await expect(card.getByLabel("Advance to").locator("option[value=enrolled]")).toHaveCount(0);
  await card.getByLabel("Advance to").selectOption("eligibility_evaluation");
  await card.getByRole("button", { name: "Advance", exact: true }).click();
  await expect(card.getByRole("status")).toContainText("Application advanced");

  await agency.goto("/overseas/agent/applications");
  await agency.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  await expect(agency.getByRole("region", { name: new RegExp(`^${name} — `) }).locator("dd", { hasText: new RegExp(`^${counselorName}$`) })).toBeVisible();
});
