import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-043 (DEC-SCOPE-317) -- the counselor's "My students" card lists a walk-in and a self-registered student whose application is
// assigned to them, each with its source; the Source filter and the search narrow the list, and Clear brings both back. Requires the
// stack running with `python -m app.seed` applied. The spec makes its own counselor and students, so no seeded record changes.

for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
  test(`a counselor filters My students by source and search (${viewport.width}px)`, async ({ page, request }) => {
    test.setTimeout(90_000);
    await page.setViewportSize(viewport);
    const consoleErrors: string[] = [];
    page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
    const unique = `${Date.now()}${viewport.width}`;
    const walkIn = `Walk ${unique}`;
    const selfRegistered = `Self ${unique}`;

    await signInAsFreshCounselor(page, "ccrm043");
    const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;
    expect((await page.request.post("/api/v1/counselor/students", { data: { full_name: walkIn, email: `ccrm043-w-${unique}@example.local` } })).status()).toBe(201);

    // A student registers on the portal and applies with this counselor (`request` keeps its own session).
    const email = `ccrm043-s-${unique}@example.local`;
    expect((await request.post("/api/v1/auth/register", { data: { email, password: "Sup3r-Secret-Pass!", full_name: selfRegistered, division: "overseas", account_type: "student" } })).ok()).toBeTruthy();
    expect((await request.post("/api/v1/auth/login", { data: { email, password: "Sup3r-Secret-Pass!", division: "overseas" } })).ok()).toBeTruthy();
    const universities = (await (await request.get("/api/v1/public/universities")).json()) as { id: string }[];
    expect((await request.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, counselor_id: counselorId } })).status()).toBe(201);

    await page.goto("/overseas/counselor/students");
    await expect(page.getByRole("heading", { name: "My students" })).toBeVisible();
    const row = (name: string) => page.getByRole("listitem").filter({ hasText: name });
    await expect(row(walkIn)).toContainText("Walk-in");
    await expect(row(walkIn)).toContainText("0 applications");
    await expect(row(selfRegistered)).toContainText("Self-registered");
    await expect(row(selfRegistered)).toContainText("1 application");
    await expect(row(selfRegistered).getByRole("button", { name: /Resend|Edit/ })).toHaveCount(0);

    const filters = page.getByRole("search", { name: "Filter my students" });
    await filters.getByLabel("Source").selectOption("self_registered");
    await expect(row(selfRegistered)).toBeVisible();
    await expect(row(walkIn)).toHaveCount(0);

    await filters.getByLabel("Source").selectOption("");
    await filters.getByLabel("Search").fill(walkIn.toUpperCase());
    await filters.getByRole("button", { name: "Search" }).click();
    await expect(row(walkIn)).toBeVisible();
    await expect(row(selfRegistered)).toHaveCount(0);

    await filters.getByLabel("Source").selectOption("agency");
    await expect(page.getByText("No students match these filters.")).toBeVisible();
    await filters.getByRole("button", { name: "Clear" }).click();
    await expect(row(walkIn)).toBeVisible();
    await expect(row(selfRegistered)).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(consoleErrors).toEqual([]);
  });
}
