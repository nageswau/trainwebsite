import { test, expect, type Page } from "@playwright/test";
import { pickFromList } from "./helpers/pick";

// ccrm-044 (DEC-SCOPE-318): the seeded walk-in (csc-001 link, no application) messages their counselor, who picks them in Counselor
// Chat and replies; the student sees the reply. The counselor cannot send to a student outside their caseload.

async function loginAs(page: Page, email: string, dashboardPath: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${dashboardPath}`);
}

test("a walk-in student and their counselor chat both ways (ccrm-044 AC1, AC2)", async ({ page }) => {
  const marker = `ccrm-044 walk-in message ${Date.now()}`;
  const replyMarker = `ccrm-044 counselor reply ${Date.now()}`;

  await loginAs(page, "student.walkin@edusphere.local", "/overseas/student/dashboard");
  await page.goto("/overseas/student/counselor-chat");
  const sendCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Send message to counselor" }) });
  await sendCard.getByLabel("Message").fill(marker);
  await sendCard.getByRole("button", { name: "Send message to counselor" }).click();
  await expect(sendCard.getByText("Message sent to your counselor.")).toBeVisible();

  await loginAs(page, "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/counselor-chat");
  const replyCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Reply to a student" }) });
  await pickFromList(replyCard.getByRole("combobox", { name: "Student" }), "Vikram Walk-in");
  await expect(replyCard.getByText(marker)).toBeVisible();
  await replyCard.getByLabel("Reply").fill(replyMarker);
  await replyCard.getByRole("button", { name: "Send reply" }).click();
  await expect(replyCard.getByText("Reply sent.")).toBeVisible();

  await loginAs(page, "student.walkin@edusphere.local", "/overseas/student/dashboard");
  await page.goto("/overseas/student/counselor-chat");
  await expect(page.getByText(replyMarker)).toBeVisible();
});

test("a counselor cannot message a student outside their caseload (ccrm-044 AC4)", async ({ page, request }) => {
  // A fresh self-registered overseas student is in nobody's caseload.
  const email = `ccrm044-${Date.now()}@example.local`;
  const registered = await request.post("/api/v1/auth/register", { data: { email, password: "Sup3r-Secret-Pass!", full_name: "Ccrm Outsider", division: "overseas", account_type: "student" } });
  expect(registered.status()).toBe(201);
  await loginAs(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  const found = await (await page.request.get(`/api/v1/lookups/overseas-students?q=${encodeURIComponent(email)}`)).json();
  const outsiderId = found.items[0].id;
  await loginAs(page, "counselor@edusphere.local", "/overseas/counselor/dashboard");
  const lookup = await (await page.request.get(`/api/v1/lookups/overseas-students?q=${encodeURIComponent(email)}`)).json();
  expect(lookup.items).toEqual([]);
  const response = await page.request.post("/api/v1/communications/messages", { data: { recipient_id: outsiderId, body: "Hi", context_type: "counselor_chat" } });
  expect(response.status()).toBe(403);
});
