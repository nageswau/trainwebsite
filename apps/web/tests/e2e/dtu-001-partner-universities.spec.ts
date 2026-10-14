import { expect, test } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// dtu-001 -- the Overseas Admin sets an agent commission on a catalogue university; the agency Master sees it on Partner
// Universities ("Agent commission" column and field), the agency's staff see the same page without it. Requires the stack running
// with `python -m app.seed` applied (and, for the real tie-ups, `python -m app.direct_tieups.load`; this spec uses the seeded
// University of Manchester so it also runs on a stack where the loader has not been run). Unique agency per run (shared E2E DB).
test("Master sees the Agent commission on Partner Universities after an admin sets it; staff do not (dtu-001)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "dtu001");
  const staffEmail = `dtu001-s-${unique}@example.local`;

  // The Overseas Admin sets 13.5 % on the University of Manchester through the dedicated route (its own browser context).
  const adminContext = await browser.newContext();
  const login = await adminContext.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const universities = await (await adminContext.request.get("/api/v1/public/universities")).json();
  const manchester = universities.find((u: { slug: string }) => u.slug === "university-of-manchester");
  expect(manchester).toBeTruthy();
  const set = await adminContext.request.put(`/api/v1/partnership/universities/${manchester.id}/agent-commission`, { data: { percent: "13.50", note: "e2e" } });
  expect(set.status()).toBe(200);
  expect((await set.json()).university.agent_commission.percent).toBe("13.50");
  await adminContext.close();

  // The Master: the column, then the detail field.
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/partner-universities");
  await page.getByLabel("Search partner universities").fill("Manchester");
  const masterRow = page.getByRole("row", { name: /University of Manchester/ });
  await expect(page.getByRole("columnheader", { name: "Agent commission" })).toBeVisible();
  await expect(masterRow).toContainText("13.50%");
  await masterRow.getByRole("button", { name: "University of Manchester" }).click();
  await expect(page.getByRole("region", { name: "Partner university" }).getByText("Agent commission", { exact: true })).toBeVisible();

  // Staff of the same agency: the same page, no commission column and no commission field.
  const created = await page.request.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "Dtu Staff", email: staffEmail } });
  expect(created.status()).toBe(201);
  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/partner-universities");
  await staff.getByLabel("Search partner universities").fill("Manchester");
  await expect(staff.getByRole("row", { name: /University of Manchester/ })).toBeVisible();
  await expect(staff.getByRole("columnheader", { name: "Agent commission" })).toHaveCount(0);
  await staff.getByRole("button", { name: "University of Manchester" }).click();
  await expect(staff.getByRole("region", { name: "Partner university" }).getByRole("heading", { name: /University of Manchester/ })).toBeVisible();
  await expect(staff.getByText("Agent commission")).toHaveCount(0);
  const api = await staff.request.get(`/api/v1/workflows/overseas/agent/crm/partner-universities/${manchester.id}`);
  expect(api.status()).toBe(200);
  expect(JSON.stringify(await api.json())).not.toContain("agent_commission");
  await staffContext.close();
});
