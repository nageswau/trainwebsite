import { test, expect, type Page } from "@playwright/test";

// RAID.md I-19: the Overseas Student's "Counselor Chat" page only ever showed
// read-only history -- no way to send a message. The Counselor role had no nav entry
// for this at all, so even if the student could send, nobody could ever see or reply.
// Confirms the full round trip: student sends (counselor resolved server-side from
// their own assigned application, no picker needed), counselor picks the student and
// replies (a real picker, not a raw id), and the student sees the reply.

async function loginAs(page: Page, email: string, password: string, dashboardPath: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${dashboardPath}`);
}

test("student sends a message to their counselor, and the counselor can reply", async ({ page }) => {
  const marker = `I19 E2E message ${Date.now()}`;
  const replyMarker = `I19 E2E reply ${Date.now()}`;

  await loginAs(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  await page.goto("/overseas/student/counselor-chat");
  const sendCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Send message to counselor" }) });
  await sendCard.getByLabel("Message").fill(marker);
  await sendCard.getByRole("button", { name: "Send message to counselor" }).click();
  await expect(sendCard.getByText("Message sent to your counselor.")).toBeVisible();

  await loginAs(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/counselor-chat");
  const replyCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Reply to a student" }) });
  await replyCard.getByLabel("Student").selectOption({ label: "Ananya Sharma" });
  await expect(replyCard.getByText(marker)).toBeVisible();
  await replyCard.getByLabel("Reply").fill(replyMarker);
  await replyCard.getByRole("button", { name: "Send reply" }).click();
  await expect(replyCard.getByText("Reply sent.")).toBeVisible();

  await loginAs(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  await page.goto("/overseas/student/counselor-chat");
  await expect(page.getByText(replyMarker)).toBeVisible();
});

test("counselor chat requires authentication", async ({ page }) => {
  await page.goto("/overseas/counselor/counselor-chat");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
