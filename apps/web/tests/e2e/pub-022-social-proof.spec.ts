import { expect, type Page, test } from "@playwright/test";

// PUB-022 (DEC-SCOPE-210) -- a Super Admin adds a testimonial, records consent, publishes and features it; it then shows in the
// homepage strip on / and /it (not /overseas), and the strip fits a 375px phone. Requires the stack running with `python -m app.seed`.
// The shared E2E DB keeps earlier runs' rows, so the story is made unique and given the lowest homepage order.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await expect(page.getByRole("heading", { name: "Administration sign-in" })).toBeVisible();
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

test("a consented, published, featured testimonial appears on / and /it (PUB-022)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const name = `PUB022 Learner ${Date.now()}`;
  await superAdmin(page);
  await page.goto("/admin/testimonials");
  await expect(page.getByRole("heading", { name: "Testimonials", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rating badge" })).toBeVisible();

  await page.getByRole("button", { name: "Add testimonial" }).first().click();
  await page.getByLabel("Division").selectOption("it");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Headline").fill("Placed after training");
  await page.getByLabel("Course / university (optional)").fill("Python Full-Stack");
  await page.getByLabel("Homepage order (lower shows first)").fill("-99999");
  await page.getByLabel("Quote").fill("The mentors and mock interviews made the difference.");
  const publish = page.getByRole("checkbox", { name: "Publish testimonial" });
  await expect(publish).toBeDisabled();
  await page.getByRole("checkbox", { name: /I confirm this person agreed/ }).check();
  await publish.check();
  await page.getByRole("checkbox", { name: /Show on homepage/ }).check();
  await page.getByRole("button", { name: "Add testimonial" }).last().click();
  await expect(page.getByText("Testimonial added.")).toBeVisible();

  try {
    // Public pages are revalidated every 60 s, so a fresh browser context reads them; poll until the new story is in.
    const visitor = await browser.newContext();
    const pub = await visitor.newPage();
    await expect(async () => {
      await pub.goto("/it");
      await expect(pub.getByText(name)).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 90_000 });
    await pub.goto("/");
    await expect(pub.getByText(name)).toBeVisible();
    await pub.goto("/overseas");
    await expect(pub.getByText(name)).toHaveCount(0);

    await pub.setViewportSize({ width: 375, height: 800 });
    await pub.goto("/it");
    await expect(pub.getByText(name)).toBeVisible();
    const overflow = await pub.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await visitor.close();

    // Delete permanently through the screen (SP9).
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "Delete permanently" }).click();
    await expect(page.getByText("Testimonial deleted.")).toBeVisible();
  } finally {
    // Whatever failed above, never leave a published e2e story at the top of the live homepage strip.
    const rows: { id: string; person_name: string }[] = await (await page.request.get("/api/v1/cms/manage/testimonials")).json().catch(() => []);
    for (const r of rows.filter((x) => x.person_name === name)) await page.request.delete(`/api/v1/cms/testimonials/${r.id}`);
  }
});
