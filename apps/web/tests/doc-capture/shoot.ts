import { mkdirSync } from "node:fs";
import path from "node:path";

import type { Locator, Page } from "@playwright/test";

// Documentation screenshots (docs/documentation-plan.md S2.3). Saved to docs/screenshots/<module>/<file>.
const ROOT = path.resolve(__dirname, "../../../../docs/screenshots");

// Every capture masks password inputs and the dev-only "Demo accounts" card (it prints the demo password).
export async function shoot(page: Page, module: string, file: string, opts: { mask?: Locator[]; fullPage?: boolean } = {}) {
  mkdirSync(path.join(ROOT, module), { recursive: true });
  const mask = [page.locator('input[type="password"]'), page.locator(".card", { hasText: "Demo accounts" }), ...(opts.mask ?? [])];
  await page.screenshot({ path: path.join(ROOT, module, file), mask, fullPage: opts.fullPage ?? false, animations: "disabled" });
}

// Passwords come from the shell, never from the repo: DOCS_PASSWORD (seeded accounts), DOCS_TEST_PASSWORD (accounts created for the docs).
export function password(kind: "seed" | "test" = "seed"): string {
  const value = kind === "seed" ? process.env.DOCS_PASSWORD : process.env.DOCS_TEST_PASSWORD;
  if (!value) throw new Error(kind === "seed" ? "Set DOCS_PASSWORD" : "Set DOCS_TEST_PASSWORD");
  return value;
}

export async function signIn(page: Page, email: string, kind: "seed" | "test" = "seed", landing = /\/overseas\/(agent|admin)\//) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password(kind));
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}
