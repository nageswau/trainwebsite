import { test, expect } from "@playwright/test";

// ADM-006 -- Certificate administration. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.
//
// nehn-031 (DEC-ROLE-003, DEC-SCOPE-297) moved issuance to the Coordinator: the admin's and the trainer's "Issue certificate"
// cards are gone, so their two specs were retired here. The override-with-a-reason path, the admin thresholds page and the
// trainer/admin 403s are covered by `nehn-031-certificate-workflow.spec.ts`.

test("certificates administration requires authentication", async ({ page }) => {
  await page.goto("/it/admin/certificates");
  await expect(page).toHaveURL(/\/it\/login/);
});
