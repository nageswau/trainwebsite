import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-023 (DEC-SCOPE-029) -- an Overseas Admin downgrades a Platinum school to Gold through the confirmation step; the
// school's Coordinator and Principal are each told exactly what was lost.

async function signIn(page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("downgrade asks for confirmation and notifies the coordinator and principal (ENH-023)", async ({ page }) => {
  test.setTimeout(150_000);
  const unique = Date.now();
  const coordinatorEmail = `enh023-e2e-coord-${unique}@example.local`;
  const principalEmail = `enh023-e2e-principal-${unique}@example.local`;
  const principalPassword = "Sup3r-Secret-Pass!";

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-023 School ${unique}`);
  await page.selectOption("#school-tier", "platinum");
  await page.fill("#school-coordinator-name", "E2E ENH-023 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  const created = page.getByText(/School created\. School code [A-Z0-9]{8}\./);
  await expect(created).toBeVisible();
  const schoolCode = (await created.textContent())!.match(/School code ([A-Z0-9]{8})/)![1];

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  const invite = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E ENH-023 Principal", email: principalEmail } });
  expect(invite.ok()).toBeTruthy();
  const token = (await invite.json()).development_invite_token;
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", principalPassword);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-lookup-code", schoolCode);
  await page.click('button:has-text("Look up")');
  await page.selectOption("#edit-tier", "gold");
  await page.click('button:has-text("Save changes")');
  const confirmBlock = page.getByRole("group", { name: /Downgrading .* from Platinum to Gold\./ });
  await expect(confirmBlock.getByRole("listitem").filter({ hasText: "Visa support" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm downgrade" })).toBeFocused();
  await page.keyboard.press("Enter"); // keyboard-only confirm, the path a screen-reader or keyboard user takes
  await expect(page.getByText("School profile updated. Partnership is now Gold.")).toBeVisible();

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.goto("/school/coordinator/notifications");
  await expect(page.getByText("Your partnership changed from Platinum to Gold")).toBeVisible();

  await signIn(page, principalEmail, principalPassword, "/school/principal/dashboard");
  await page.goto("/school/principal/notifications");
  await expect(page.getByText("Your partnership changed from Platinum to Gold")).toBeVisible();
});
