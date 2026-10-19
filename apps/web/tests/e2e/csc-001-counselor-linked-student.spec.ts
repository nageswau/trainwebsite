import { test, expect, type Page } from "@playwright/test";

// csc-001 (DEC-SCOPE-226) -- a student linked to the counselor (no application) is in the counselor's Student reference picker, can be
// booked, and the booking shows in the counselor's Student appointments list (QA-01). Requires the stack running via `docker compose up`
// with `python -m app.seed` applied (it links "Vikram Walk-in" to the demo counselor).

const WALK_IN = "Vikram Walk-in";

async function loginAsCounselor(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");
}

async function walkInId(page: Page): Promise<string> {
  const response = await page.request.get("/api/v1/lookups/overseas-students", {
    params: { q: WALK_IN },
  });
  expect(response.status()).toBe(200);
  const { items } = await response.json();
  expect(items.map((item: { label: string }) => item.label)).toEqual([WALK_IN]);
  return items[0].id;
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 375, height: 812 },
]) {
  test(`counselor books a linked walk-in student from the picker and sees the booking (${viewport.width}px)`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on(
      "console",
      (message) =>
        message.type() === "error" && consoleErrors.push(message.text()),
    );
    await page.setViewportSize(viewport);
    await loginAsCounselor(page);
    const studentId = await walkInId(page);
    await page.goto("/overseas/counselor/appointments");

    const form = page
      .locator("form")
      .filter({
        has: page.getByRole("button", { name: "Schedule appointment" }),
      });
    await form
      .getByRole("combobox", { name: "Student reference" })
      .fill("Walk-in");
    await page.getByRole("option", { name: new RegExp(WALK_IN) }).click();
    await form.locator("input[type=datetime-local]").fill("2027-04-12T10:30");
    await form.getByRole("button", { name: "Schedule appointment" }).click();
    await expect(page.getByText("Appointment scheduled.")).toBeVisible();

    await page.reload();
    await expect(
      page.getByRole("cell", { name: studentId }).first(),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    expect(consoleErrors).toEqual([]);
  });
}
