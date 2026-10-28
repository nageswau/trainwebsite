import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-047: the intake is a month + year picker -- an overseas telecaller's new lead (AC1, shown on the lead's qualification), a
// counselor editing a student's intake (AC3), and the student's apply form (AC4, a half-chosen intake is refused before sending).
test.describe.configure({ timeout: 120_000 });

const YEAR = String(new Date().getFullYear() + 1);
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function overseasTelecaller(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Intake47 Manager ${stamp}`, email: `ccrm047-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Intake47 Telecaller ${stamp}`, email: `ccrm047-t-${stamp}@example.local`,
      telecaller_profile: { team: "overseas", employee_id: `IP-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await page.goto("/overseas/login");
  await page.fill("#login-email", caller.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/telecaller/dashboard");
}

test("an overseas telecaller creates a lead with an intake and the lead shows it (AC1)", async ({ page }) => {
  const stamp = Date.now();
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await overseasTelecaller(page, stamp);

  await page.goto("/telecaller/leads/new");
  await page.getByLabel(/Student name/).fill(`Intake Lead ${stamp}`);
  await page.getByLabel(/Mobile number/).fill(`7${String(stamp).slice(-9)}`);
  await expect(page.getByLabel("Intake month")).toHaveCount(0); // no product yet: no intake
  await page.getByLabel(/Product interest/).selectOption({ label: "UK" });
  await page.getByLabel(/Lead source/).selectOption("instagram");
  await page.getByLabel("Intake month").selectOption("Sep");
  await page.getByRole("button", { name: "Create lead" }).click();
  await expect(page.getByText("Choose both the month and the year for the intake.")).toBeVisible();
  await page.getByLabel("Intake year").selectOption(YEAR);
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/telecaller\/leads\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("region", { name: "Qualification" }).getByText(`Sep ${YEAR}`)).toBeVisible();
  expect(errors).toEqual([]);

  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/telecaller/leads/new");
  await page.getByLabel(/Product interest/).selectOption({ label: "UK" });
  await expect(page.getByLabel("Intake year")).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});

test("a counselor sets a student's intake with the picker (AC3)", async ({ page }) => {
  const unique = Date.now();
  const student = `Intake Student ${unique}`;
  await signInAsFreshCounselor(page, "ccrm047");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `ccrm047-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()).student;

  await page.goto(`/overseas/counselor/students/${id}/profile`);
  await expect(page.getByRole("heading", { name: `Profile: ${student}` })).toBeVisible();
  await page.getByLabel("Intake month").selectOption("Jan");
  await page.getByLabel("Intake year").selectOption(YEAR);
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Intake month")).toHaveValue("Jan");
  await expect(page.getByLabel("Intake year")).toHaveValue(YEAR);
});

test("the student's apply form takes a month + year intake (AC4)", async ({ page }) => {
  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  await page.goto("/overseas/student/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) });
  await expect(card.locator("#apply-university option")).not.toHaveCount(0);
  await card.locator("#apply-university").selectOption({ index: 1 });
  await card.getByLabel("Intake month").selectOption("Sep");
  await card.getByRole("button", { name: "Submit interest" }).click();
  await expect(card.getByText("Choose both the month and the year for the intake.")).toBeVisible();
  await expect(card.getByLabel("Intake year").locator("option")).toHaveCount(5); // "Year" + this year .. three years ahead
});
