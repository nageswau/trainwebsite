import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-038 (DEC-SCOPE-272 CA4-CA7): the overseas counselor's calendar feed on their sidebar "Calendar". Seeded demo accounts; the feed is
// one row per counselor, so each test first turns it off through the API to start from "Off".

const COUNSELOR = ["counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard"] as const;
const FEED_API = "/api/v1/counselor/calendar-feed";

async function startOff(page: Page) {
  expect((await page.request.delete(FEED_API)).status()).toBe(204);
}

test.describe.configure({ mode: "serial" }); // one shared feed row for the demo counselor

test("the counselor creates a link that serves an iCal feed, regenerates it and turns it off", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signIn(page, ...COUNSELOR);
  await startOff(page);
  await page.getByRole("link", { name: "Calendar", exact: true }).click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/calendar$/);
  await expect(page.getByRole("heading", { name: "Calendar", level: 2 })).toBeVisible();
  await expect(page.getByText("Status: Off")).toBeVisible();

  await page.getByRole("button", { name: "Create calendar link" }).click();
  const link = page.getByLabel("Your calendar link");
  await expect(link).toHaveValue(/\/api\/v1\/calendar\/feeds\/[\w-]+\.ics$/);
  const first = await link.inputValue();
  const feed = await page.request.get(new URL(first).pathname); // the token is the credential
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  expect(await feed.text()).toContain("BEGIN:VCALENDAR");

  await page.reload(); // shown once
  await expect(page.getByLabel("Your calendar link")).toHaveCount(0);
  await expect(page.getByText(/Status: On/)).toBeVisible();

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Create a new link" }).click();
  await expect(page.getByLabel("Your calendar link")).not.toHaveValue(first);
  expect((await page.request.get(new URL(first).pathname)).status()).toBe(404);

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Turn off feed" }).click();
  await expect(page.getByRole("status")).toContainText("The calendar feed is off");
  expect(errors).toEqual([]);
});

test("declining the regenerate prompt keeps the current link", async ({ page }) => {
  await signIn(page, ...COUNSELOR);
  await startOff(page);
  await page.goto("/overseas/counselor/calendar");
  await page.getByRole("button", { name: "Create calendar link" }).click();
  const first = await page.getByLabel("Your calendar link").inputValue();
  page.once("dialog", (d) => d.dismiss());
  await page.getByRole("button", { name: "Create a new link" }).click();
  await expect(page.getByLabel("Your calendar link")).toHaveValue(first);
  expect((await page.request.get(new URL(first).pathname)).status()).toBe(200);
  await startOff(page);
});

test("the Overseas Admin is refused and the API refuses them too", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/counselor/calendar");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  expect((await page.request.post(FEED_API)).status()).toBe(403);
});

test("the page fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, ...COUNSELOR);
  await startOff(page);
  await page.goto("/overseas/counselor/calendar");
  await page.getByRole("button", { name: "Create calendar link" }).click();
  await expect(page.getByLabel("Your calendar link")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await startOff(page);
});
