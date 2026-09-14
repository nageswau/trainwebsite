import { test, expect } from "@playwright/test";

// TRN-001, tester feedback 2026-09-04 (WhatsApp, RAID.md I-15): "on DASHBOARD one table
// was coming outside from alignment". Reproduced directly at a 390px viewport before
// fixing: the Trainer's own 9-item portal nav (Dashboard/Attendance/Assignments/
// Assessments/Materials/Live Sessions/Student Progress/Questions/Support) became a
// fixed bottom bar with horizontal scroll and zero visible affordance -- it truncated
// mid-word at "Mate[rials]" with a hard clipped edge, which reads exactly like a
// misaligned/broken table to a non-technical user. RESPONSIVE_RULES.md's baseline rule
// (NFR-RESP-001, CONFIRMED_CURRENT) requires "Primary action always reachable without
// horizontal scroll... collapses behind a toggle" -- fixed in PortalShell.tsx by reusing
// the exact same toggle+dropdown pattern already proven for the public site's own
// mobile nav (MobileNavToggle), not a new interaction. This is a shared layout
// component (PortalShell), so the fix applies to every role's portal, not just
// Trainer's -- this spec covers the role that actually reported it.

test("Trainer's full 9-item nav is reachable via a toggle at a 390px viewport, no horizontal scroll (RESPONSIVE_RULES.md baseline)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  // the old fixed bottom bar is gone entirely, not just relabeled
  await expect(page.locator(".sidebar")).toBeHidden();
  const bodyOverflow = await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth);
  expect(bodyOverflow).toBe(0);

  const toggle = page.locator("button.portal-mobile-menu");
  await expect(toggle).toBeVisible();
  await toggle.click();

  const panel = page.locator(".portal-mobile-nav-panel");
  for (const label of ["Dashboard", "Attendance", "Assignments", "Assessments", "Materials", "Live Sessions", "Student Progress", "Questions", "Support"]) {
    await expect(panel.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
});

test("the mobile nav panel closes after navigating (no leftover overlay on the destination page)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.locator("button.portal-mobile-menu").click();
  await page.locator(".portal-mobile-nav-panel").getByRole("link", { name: "Attendance", exact: true }).click();
  await page.waitForURL("**/it/trainer/attendance");
  await expect(page.locator(".portal-mobile-nav-panel")).toBeHidden();
});

test("the tablet range (640-980px) shows real readable nav labels via the same toggle, not unlabeled bullets (RAID.md I-17)", async ({ page }) => {
  // RAID.md I-17, found investigating I-15: a second, distinct gap in the 640-980px
  // tablet range -- the sidebar stayed visible but narrowed to an 82px icon-only strip
  // where `.portal-nav a{font-size:0}` replaced every nav item's label with an identical
  // unlabeled "•" bullet, indistinguishable from each other. Fixed by extending the same
  // toggle+drawer pattern (RESPONSIVE_RULES.md's own "icon+label or drawer" tablet
  // guidance) up to the existing 980px breakpoint instead of showing the icon-only strip.
  await page.setViewportSize({ width: 800, height: 900 });
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await expect(page.locator(".sidebar")).toBeHidden();
  const bodyOverflow = await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth);
  expect(bodyOverflow).toBe(0);

  const toggle = page.locator("button.portal-mobile-menu");
  await expect(toggle).toBeVisible();
  await toggle.click();

  const panel = page.locator(".portal-mobile-nav-panel");
  for (const label of ["Dashboard", "Attendance", "Assignments", "Assessments", "Materials", "Live Sessions", "Student Progress", "Questions", "Support"]) {
    await expect(panel.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
});

test("the desktop sidebar is unaffected above the mobile breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await expect(page.locator("aside.sidebar")).toBeVisible();
  await expect(page.locator("button.portal-mobile-menu")).toBeHidden();
});
