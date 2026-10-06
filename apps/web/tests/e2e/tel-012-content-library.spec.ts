import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-012 (AC1-AC5, DEC-SCOPE-076 C1-C4): a telecaller manager keeps the call scripts, message templates and brochures; a brochure
// link opens signed out until the brochure is deactivated; a telecaller reads the library but cannot open the manager screens.
// Throwaway accounts via the real admin API; every name carries a stamp because the database is shared.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

async function accounts(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Lib Manager ${stamp}`, email: `tel012-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Lib Telecaller ${stamp}`, email: `tel012-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `TL-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("manager: scripts, templates and a brochure whose link works signed out until deactivated; telecaller reads only", async ({ page, playwright, baseURL }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const errors: string[] = [];
  // The browser itself logs each 4xx this spec provokes on purpose (409/422); any other console error fails the test.
  page.on("console", (m) => { if (m.type() === "error" && !/status of (409|422)/.test(m.text())) errors.push(m.text()); });
  const { manager, caller } = await accounts(page, stamp);
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");

  // Scripts: the seeded §6 script (AC1), and a second active script for the same product is refused (C3).
  await page.getByRole("link", { name: "Scripts" }).first().click();
  await page.waitForURL("**/telecaller/manager/scripts");
  await expect(page.getByRole("row", { name: /Cyber Security standard script/ }).first()).toContainText("Fix counselling appointment");
  await page.getByLabel("Product (required)").selectOption({ label: "Cyber Security" });
  await page.getByLabel("Script name (required)").fill(`Second ${stamp}`);
  await page.getByLabel("Step 1 title").fill("Introduction");
  await page.getByRole("button", { name: "Create script" }).click();
  await expect(page.locator("#script-create-feedback")).toContainText("already has an active script");

  // Brochures: a PDF uploads; a non-PDF is refused (AC5).
  await page.getByRole("link", { name: "Brochures" }).first().click();
  await page.waitForURL("**/telecaller/manager/brochures");
  const brochure = `Cyber brochure ${stamp}`;
  await page.getByLabel("Brochure name (required)").fill(brochure);
  await page.getByLabel("PDF file (required)").setInputFiles({ name: "photo.pdf", mimeType: "application/pdf", buffer: Buffer.from("\x89PNG not a pdf") });
  await page.getByRole("button", { name: "Upload brochure" }).click();
  await expect(page.locator("#asset-create-feedback")).toHaveText("Upload a PDF file");
  await page.getByLabel("PDF file (required)").setInputFiles({ name: "cyber.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByRole("button", { name: "Upload brochure" }).click();
  await expect(page.locator("#asset-create-feedback")).toHaveText(`Uploaded ${brochure}.`);

  // Templates: an unknown placeholder is refused (AC3); a template with the brochure previews a working link (AC2, AC4).
  await page.getByRole("link", { name: "Templates" }).first().click();
  await page.waitForURL("**/telecaller/manager/templates");
  await expect(page.getByRole("row", { name: /^Welcome message WhatsApp/ }).first()).toBeVisible(); // AC1 seed
  const name = `Course ${stamp}`;
  await page.getByLabel("Kind (required)").selectOption("course_details");
  await page.getByLabel("Template name (required)").fill(name);
  await page.getByLabel("Brochure", { exact: true }).selectOption({ label: brochure });
  await page.getByLabel("Message (required)").fill("Hi {first_name}: {brochure_link}");
  await expect(page.getByText("Unknown placeholder: {first_name}")).toBeVisible();
  await page.getByRole("button", { name: "Create template" }).click();
  await expect(page.locator("#tpl-create-feedback")).toContainText("Unknown placeholder {first_name}");
  await page.getByLabel("Message (required)").fill("Hi {name}: {brochure_link}");
  await page.getByRole("button", { name: "Create template" }).click();
  await expect(page.locator("#tpl-create-feedback")).toHaveText(`Created ${name}.`);
  await page.getByLabel("Show").selectOption("whatsapp");
  await page.waitForURL("**/telecaller/manager/templates?channel=whatsapp");
  await page.getByRole("button", { name: `Preview ${name}` }).click();
  const preview = page.getByRole("region", { name: `Preview of ${name}` });
  await expect(preview).toContainText("Hi Priya Sharma: http");
  const link = (await preview.innerText()).match(/https?:\/\/\S+telecaller-assets\/\S+/)![0];
  const path = new URL(link).pathname; // the link is absolute on FRONTEND_URL; open it on this test's origin

  const anonymous = await playwright.request.newContext({ baseURL }); // no cookies: a lead's browser
  const open = await anonymous.get(path);
  expect(open.status()).toBe(200);
  expect(open.headers()["content-type"]).toBe("application/pdf");

  // Deactivating the brochure ends the link at once (C1).
  await page.getByRole("link", { name: "Brochures" }).first().click();
  await page.getByRole("button", { name: `Deactivate ${brochure}` }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByRole("button", { name: `Reactivate ${brochure}` })).toBeFocused();
  const gone = await anonymous.get(path);
  expect(gone.status()).toBe(404);
  await anonymous.dispose();

  // A telecaller reads the library through the API but cannot open the manager screens (AC6).
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  expect((await page.request.get("/api/v1/telecaller/templates")).status()).toBe(200);
  expect((await page.request.post("/api/v1/telecaller/templates", { data: { channel: "whatsapp", kind: "welcome", name: "x", body: "x" } })).status()).toBe(403);
  await page.goto("/telecaller/manager/templates");
  await expect(page.getByText("Telecaller manager role required")).toBeVisible();
  expect(errors).toEqual([]);
});

test("library screens fit a phone without side scroll", async ({ page }) => {
  test.setTimeout(60_000);
  const { manager } = await accounts(page, Date.now());
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  for (const screen of ["scripts", "templates", "brochures"]) {
    await page.goto(`/telecaller/manager/${screen}`);
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});
