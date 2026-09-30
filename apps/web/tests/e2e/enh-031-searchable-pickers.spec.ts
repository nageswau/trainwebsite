import { expect, test } from "@playwright/test";

import { pickFromList } from "./helpers/pick";

// ENH-031 (DEC-SCOPE-037): an agent links a student through the 3-character search, creates an application with the
// load-once picker, and Overseas Admin finds that application by searching the student's name. Uses the seeded demo
// agent (active agency) and Overseas Admin.
async function signIn(page: import("@playwright/test").Page, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("pick references instead of typing ids: agent link, agent application, admin update (ENH-031)", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const name = `E2E ENH031 Student ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  const created = await page.request.post("/api/v1/admin/users", { data: { full_name: name, email: `enh031-${unique}@example.local`, division: "overseas", role: "overseas_student" } });
  expect(created.ok()).toBeTruthy();

  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/students");
  const link = page.getByRole("combobox", { name: "Overseas student reference" });
  await link.click();
  await link.fill("E2");
  await expect(page.getByText("Type at least 3 characters.")).toBeVisible();
  await pickFromList(link, name, new RegExp(`^${name} — e\\*\\*\\*@example\\.local$`));
  await page.getByRole("button", { name: "Link student" }).click();
  await expect(page.getByText("Student linked.")).toBeVisible();

  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — `));
  await page.locator("#agent-app-university").selectOption({ index: 1 });
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByText("Application created.")).toBeVisible();

  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/applications");
  // Overseas Admin's "applications" section is the operational "Update application" card (F5); F8 is Super Admin's.
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Update application" }) });
  await card.getByRole("button", { name: "Update application" }).click();
  await expect(card.getByText("Choose an application from the list.")).toBeVisible();
  await pickFromList(card.getByRole("combobox", { name: "Application reference" }), name, new RegExp(`^${name} — `));
  await card.getByLabel("Status").selectOption("eligibility_evaluation");
  await card.getByRole("button", { name: "Update application" }).click();
  await expect(card.getByText("Application updated and student notified.")).toBeVisible();
});

test("the open list sits below its input and never covers it (ENH-031 AC09)", async ({ page }) => {
  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/applications");
  const input = page.getByRole("combobox", { name: "Linked student" });
  await input.click();
  const list = page.locator("#agent-app-student-list");
  await expect(list).toBeVisible();
  const [inputBox, listBox] = [await input.boundingBox(), await list.boundingBox()];
  expect(listBox!.y).toBeGreaterThanOrEqual(inputBox!.y + inputBox!.height - 1);
  await input.click(); // the input stays clickable while the list is open
  await expect(input).toBeFocused();
});

test("the open list never scrolls the page sideways at 320px (ENH-031 AC09)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/applications");
  const input = page.getByRole("combobox", { name: "Linked student" });
  await input.click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
