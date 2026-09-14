import { test, expect } from "@playwright/test";

// User-reported bug: "not able to click on sub menu" on the public site's "Programs"
// header dropdown. A synthetic Playwright `.click()` never reproduced it (it teleports
// straight to the target), but a real mouse moving gradually from the trigger down
// toward a submenu link did: `.nav-dropdown-panel` had a plain CSS `margin-top` gap
// below the trigger button. A margin sits outside an element's own box, so moving the
// real cursor through that empty space left `.nav-dropdown`'s hoverable area entirely
// mid-gap, firing its `onMouseLeave` and closing the menu before the cursor ever reached
// a link. Fixed by moving that spacing to `padding-top` on the hoverable panel itself
// (with the visible white card as a separate inner element), so the gap is now part of
// the panel's own box rather than empty space outside it.

test("a real mouse trajectory from the Programs trigger down to a submenu link keeps the menu open and reaches it", async ({ page }) => {
  await page.goto("/it");
  const trigger = page.getByRole("button", { name: "Programs" });
  const box = await trigger.boundingBox();
  if (!box) throw new Error("Programs trigger not found");
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;

  // Real hover -- `.nav-dropdown` opens on `onMouseEnter`, not only on click.
  await page.mouse.move(startX, startY);
  const panel = page.locator(".nav-dropdown-panel");
  await expect(panel).toBeVisible();

  const link = panel.getByRole("link", { name: "Career Paths", exact: true });
  const linkBox = await link.boundingBox();
  if (!linkBox) throw new Error("Career Paths link not found in panel");
  const endX = linkBox.x + linkBox.width / 2;
  const endY = linkBox.y + linkBox.height / 2;

  // Move in small steps to simulate an actual human mouse path crossing the gap between
  // the trigger and the panel, rather than teleporting straight to the link.
  const steps = 20;
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(startX + ((endX - startX) * i) / steps, startY + ((endY - startY) * i) / steps);
  }
  await expect(panel).toBeVisible();

  await page.mouse.down();
  await page.mouse.up();
  await page.waitForURL("**/it/career-paths");
});

test("clicking the Programs trigger still opens the dropdown", async ({ page }) => {
  await page.goto("/it");
  await page.getByRole("button", { name: "Programs" }).click();
  await expect(page.locator(".nav-dropdown-panel")).toBeVisible();
  for (const label of ["All Programs", "Career Paths", "Real Projects", "Success Stories", "Business Services", "Webinars"]) {
    await expect(page.locator(".nav-dropdown-panel").getByRole("link", { name: label, exact: true })).toBeVisible();
  }
});
