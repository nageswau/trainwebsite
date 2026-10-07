import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-018 (DEC-SCOPE-099): an IT telecaller hands a lead to an IT counselor (HO4) and can then only read it (AC1). The counselor finds it
// under Leads, links the suggested student (same email) -- Application/Enrollment (AC3) -- unlinks it, and returns the lead with a
// reason (AC2): the telecaller works it again and sees the return in the activity. Throwaway accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("handover, student link and return between an IT telecaller and an IT counselor", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E HO Manager ${stamp}`, email: `tel018-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E HO Telecaller ${stamp}`, email: `tel018-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `HO-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E HO Counselor ${stamp}`;
  const studentName = `E2E HO Student ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `tel018-c-${stamp}@example.local` });
  const student = await post({ role: "it_student", division: "it", full_name: studentName, email: `tel018-s-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await activateWithToken(page.request, counselor.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller creates a lead with the student's email and hands it over
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  expect(products.length).toBeGreaterThan(0);
  const name = `HO Lead ${stamp}`;
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`; // random: parallel specs derive phones from the same clock
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name, email: student.email, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  await page.goto(`/telecaller/leads/${id}`);
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByText(`Handed over to ${counselorName}.`)).toBeVisible();
  await expect(page.getByRole("note")).toContainText("You can view it but not change it.");
  await expect(page.getByRole("button", { name: "Edit details" })).toHaveCount(0);
  expect((await page.request.patch(`/api/v1/telecaller/leads/${id}`, { data: { priority: "hot" } })).status()).toBe(403); // AC1

  // the counselor links the suggested student, unlinks, then returns the lead
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto("/it/counselor/leads");
  const row = page.getByRole("row", { name: new RegExp(name) });
  await row.getByRole("link").click();
  await page.waitForURL(`**/it/counselor/leads/${id}`);
  await page.getByRole("button", { name: `Link ${studentName}` }).click();
  await page.getByRole("button", { name: "Yes, link" }).click();
  await expect(page.getByText("Student linked.")).toBeVisible();
  await expect(page.getByText(/^Stage:/).first()).toContainText("Application/Enrollment");
  await expect(page.getByRole("button", { name: "Return to telecaller" })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Unlink student" }).click();
  await page.getByRole("button", { name: "Yes, unlink" }).click();
  await expect(page.getByText("Student unlinked.")).toBeVisible();
  await page.getByRole("button", { name: "Return to telecaller" }).click();
  await page.getByLabel("Reason for returning").fill("Wants to discuss the fees at home first");
  await page.getByRole("button", { name: "Return lead" }).click();
  await expect(page.getByText("Lead returned to the telecaller.")).toBeVisible();

  // the telecaller works the lead again and sees the return
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${id}`);
  await expect(page.getByRole("button", { name: "Assign to counselor" })).toBeVisible();
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity.getByText("Returned to the telecaller")).toBeVisible();
  await expect(activity.getByText("Wants to discuss the fees at home first")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
