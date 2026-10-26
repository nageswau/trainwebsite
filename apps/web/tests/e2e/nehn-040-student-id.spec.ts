import { expect, test, type Page } from "@playwright/test";

// nehn-040 (DEC-SCOPE-279) -- the Student ID is shown and searchable: the Overseas Admin finds the seeded overseas student by it on
// Users, and an agency student created with no login gets one, shown on the card and the record, and found by the agency search.
// The E2E database is shared and keeps rows: names are unique per run.

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
const CODE = /Student ID ([0-9A-F]{8})/;

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("the Overseas Admin finds a student on Users by the Student ID (nehn-040-AC1, AC3)", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  const users = await (await page.request.get("/api/v1/admin/users?role=overseas_student")).json();
  const ananya = users.find((u: { email: string }) => u.email === "student.overseas@edusphere.local");
  expect(ananya.student_code).toMatch(/^[0-9A-F]{8}$/);
  await page.goto("/overseas/admin/users");
  await page.getByLabel("Search by name, email, role, or Student ID").fill(ananya.student_code.toLowerCase());
  const row = page.getByRole("row", { name: /Ananya Sharma/ });
  await expect(row).toContainText(`Student ID ${ananya.student_code}`);
  await expect(page.getByText("1 account shown")).toBeVisible();
});

test("an agency student created with no login gets a Student ID, shown and searchable (nehn-040-AC2, AC3)", async ({ page }) => {
  const name = `E2E Coded ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${name} added.` })).toBeVisible();
  const header = page.getByRole("heading", { name, level: 4 }).locator("xpath=following-sibling::p[1]");
  const code = (await header.textContent())?.match(CODE)?.[1];
  expect(code).toBeTruthy();

  await page.getByLabel("Search students").fill(code!.toLowerCase());
  const cards = page.getByRole("list", { name: "Students" }).getByRole("listitem");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText(name);
  await expect(cards.first()).toContainText(`Student ID ${code}`);
});
