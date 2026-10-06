import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-005 (AC1, AC2, AC4, AC6): a College BDM starts an MoU, moves it Proposal Sent -> Under Negotiation -> Signed (confirmed, with a
// signed PDF) -> Active; the pipeline follows to MoU Signed; the history names each change; the manager reads and downloads but cannot
// edit; another type's BDM cannot download; nothing overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

async function signIn(page: Page, portal: "it" | "overseas" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("BDM MoU: statuses, signed document, D28 pipeline advance, history, manager read-only, scoped download", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm005-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm005-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E5-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  const outsider = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E School BDM ${stamp}`, email: `bdm005-s-${stamp}@example.local`,
            bdm_profile: { bdm_type: "school", employee_id: `E2E5S-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm, outsider]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;

  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  const card = page.getByRole("region", { name: "MoU" });
  await expect(card.getByText("No MoU yet.")).toBeVisible();

  // Start as Proposal Sent, keyboard only (the date defaults to today on the server)
  await card.getByRole("button", { name: "Start MoU" }).focus();
  await page.keyboard.press("Enter");
  await card.getByLabel("Status").selectOption("proposal_sent");
  await card.getByLabel("Reference").fill(`MOU-${stamp}`);
  await card.getByRole("button", { name: "Start MoU" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "MoU started." })).toBeVisible();
  const steps = card.getByRole("list", { name: "MoU statuses" });
  await expect(steps.getByRole("listitem").filter({ hasText: "Proposal Sent" })).toHaveAttribute("aria-current", "step");

  // Under Negotiation, then Signed: the confirmation names the pipeline stage it moves to (D28)
  await card.getByRole("button", { name: "Edit MoU" }).click();
  await card.getByLabel("Status").selectOption("under_negotiation");
  await card.getByRole("button", { name: "Save MoU" }).click();
  await expect(page.getByRole("status").filter({ hasText: "MoU saved." })).toBeVisible();
  await card.getByRole("button", { name: "Edit MoU" }).click();
  await card.getByLabel("Status").selectOption("signed");
  await expect(card.getByLabel("Signed date (required)")).toHaveAttribute("required", "");
  await card.getByLabel("Signed date (required)").fill("2026-10-01");
  await card.getByRole("button", { name: "Save MoU" }).click();
  const confirm = card.getByRole("group", { name: "Confirm signing" });
  await expect(confirm).toContainText("This also moves the pipeline to MoU Signed.");
  await confirm.getByRole("button", { name: "Yes, save" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The pipeline moved to MoU Signed." })).toBeVisible();
  await expect(page.getByRole("list", { name: "Pipeline stages" }).getByRole("listitem").filter({ hasText: "MoU Signed" })).toHaveAttribute("aria-current", "step");

  // The signed document
  await card.getByLabel(/Upload document/).setInputFiles({ name: "signed.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByRole("status").filter({ hasText: "Document saved." })).toBeVisible();
  const download = card.getByRole("link", { name: "Download document (PDF)" });
  const href = await download.getAttribute("href");
  expect(href).toMatch(/^\/api\/v1\/bdm\/mous\/[0-9a-f-]+\/document$/);
  const fetched = await page.request.get(href!);
  expect(fetched.status()).toBe(200);
  expect(fetched.headers()["content-disposition"]).toContain("attachment");

  // Active needs the window (AC2)
  await card.getByRole("button", { name: "Edit MoU" }).click();
  await card.getByLabel("Status").selectOption("active");
  await card.getByLabel("Valid from (required)").fill("2026-10-01");
  await card.getByLabel("Valid until (required)").fill("2027-09-30");
  await card.getByRole("button", { name: "Save MoU" }).click();
  await expect(steps.getByRole("listitem").filter({ hasText: "Active" })).toHaveAttribute("aria-current", "step");

  // History names each change and its actor (AC1)
  await card.getByText("MoU history").click();
  const history = card.getByRole("list", { name: "MoU history" });
  await expect(history.getByText("Under Negotiation → Signed")).toBeVisible();
  await expect(history.getByText("Document uploaded")).toBeVisible();
  await expect(history.getByText(`By E2E BDM ${stamp}`).first()).toBeVisible();
  await noOverflow(page);

  // The list shows it under Active
  await page.goto("/bdm/mous?status=active");
  await expect(page.getByRole("region", { name: "MoUs" }).getByRole("link", { name: `E2E College ${stamp}` })).toBeVisible();
  await noOverflow(page);

  // Another type's BDM cannot download (AC4: 404, as an unknown id)
  await signIn(page, "overseas", outsider.email, E2E_PASSWORD, "/bdm/my-day");
  expect((await page.request.get(href!)).status()).toBe(404);

  // The manager reads and downloads, but cannot edit
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  const managerCard = page.getByRole("region", { name: "MoU" });
  await expect(managerCard.getByText("Active", { exact: true }).first()).toBeVisible();
  await expect(managerCard.getByRole("button", { name: "Edit MoU" })).toHaveCount(0);
  await expect(managerCard.getByLabel(/Upload document|Replace document/)).toHaveCount(0);
  expect((await page.request.get(href!)).status()).toBe(200);
});
