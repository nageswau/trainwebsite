import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-013 -- a Master confirms enrollment from an offer (explicit confirmation step), the final-status badge and date warning show,
// exactly one estimated commission exists, a correction does not add one; 320 px. Unique names per run (shared E2E DB). The student
// and application set-up mirrors agn-008-agent-applications.spec.ts.
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

test("a Master confirms enrollment once; a correction adds no second commission (AC01/AC02/AC04/AC09)", async ({ page }) => {
  const name = `E2E Enrol ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");

  const detail = await applicationAtOffer(page, name);
  await detail.getByRole("button", { name: "Enroll student" }).click();
  const form = detail.getByRole("form", { name: "Enrollment" });
  await form.getByLabel("Enrollment date (required)").fill("2027-10-05");
  await form.getByLabel("University student ID (optional)").fill("UOM-123");
  await form.getByRole("button", { name: "Confirm enrollment" }).click();
  await detail.getByRole("group", { name: "Confirm enrollment" }).getByRole("button", { name: "Yes, confirm enrollment" }).click();
  await expect(detail.getByRole("status")).toHaveText("Enrollment confirmed.");
  await expect(detail.locator(".badge", { hasText: "Enrolled" })).toBeVisible();
  await expect(detail.getByText("The enrollment date is in the future and after the intake month. Check the date.")).toBeVisible();

  const commissionsFor = async () =>
    (await (await page.request.get("/api/v1/workflows/overseas/agent/commissions")).json()).filter((c: { student: string }) => c.student === name);
  expect(await commissionsFor()).toHaveLength(1);
  expect((await commissionsFor())[0].status).toBe("estimated");

  await detail.getByRole("button", { name: "Edit enrollment details" }).click();
  await detail.getByLabel("Enrollment date (required)").fill("2027-09-25");
  await detail.getByRole("button", { name: "Save enrollment details" }).click();
  await expect(detail.getByRole("status")).toHaveText("Enrollment details saved.");
  await expect(detail.getByText(/after the intake month/)).toHaveCount(0);
  expect(await commissionsFor()).toHaveLength(1);
});

test("no horizontal scroll at 320px with the enrollment form open", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const detail = await applicationAtOffer(page, `E2E Narrow ${stamp()}`);
  await detail.getByRole("button", { name: "Enroll student" }).click();
  await expect(detail.getByRole("form", { name: "Enrollment" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
