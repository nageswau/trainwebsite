import { mkdirSync } from "node:fs";
import path from "node:path";

import type { Locator, Page } from "@playwright/test";

// Documentation screenshots (docs/documentation-plan.md S2.3). Saved to docs/screenshots/<module>/<file>.
const ROOT = path.resolve(__dirname, "../../../../docs/screenshots");

// Every capture masks password inputs and the dev-only "Demo accounts" card (it prints the demo password).
export async function shoot(page: Page, module: string, file: string, opts: { mask?: Locator[]; fullPage?: boolean } = {}) {
  mkdirSync(path.join(ROOT, module), { recursive: true });
  // Also masks the dev-only reset link on the forgot-password page (it carries a live reset token).
  const mask = [
    page.locator('input[type="password"]'),
    page.locator(".card", { hasText: "Demo accounts" }),
    page.getByText("Development only", { exact: false }),
    ...(opts.mask ?? []),
  ];
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.screenshot({ path: path.join(ROOT, module, file), mask, maskColor: "#C9CED6", fullPage: opts.fullPage ?? false, animations: "disabled" });
}

// Passwords come from the shell, never from the repo: DOCS_PASSWORD (seeded accounts), DOCS_TEST_PASSWORD (accounts created for the docs).
export function password(kind: "seed" | "test" = "seed"): string {
  const value = kind === "seed" ? process.env.DOCS_PASSWORD : process.env.DOCS_TEST_PASSWORD;
  if (!value) throw new Error(kind === "seed" ? "Set DOCS_PASSWORD" : "Set DOCS_TEST_PASSWORD");
  return value;
}

// Scrolls an element to the top of the viewport (below the sticky header) before a capture.
export async function toTop(locator: Locator, offset = 80) {
  await locator.evaluate((el, off) => window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off }), offset);
}

export async function signIn(page: Page, email: string, kind: "seed" | "test" = "seed", landing = /\/overseas\/(agent|admin)\//) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password(kind));
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

// Set-password / reset links emailed to `to`, read from the docs stack's local Mailpit (no mail leaves the machine).
// `after` = how many such emails existed before the action; waits for a newer one so a used link is never returned.
export async function mailCount(to: string): Promise<number> {
  const base = process.env.DOCS_MAILPIT_URL || "http://localhost:8025";
  const list = await (await fetch(`${base}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
  return Number(list.messages_count ?? list.messages?.length ?? 0);
}

export async function mailLink(to: string, after = 0): Promise<string> {
  const base = process.env.DOCS_MAILPIT_URL || "http://localhost:8025";
  for (let i = 0; i < 40; i++) {
    const list = await (await fetch(`${base}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
    const messages = [...(list.messages ?? [])].sort((x: { Created: string }, y: { Created: string }) => y.Created.localeCompare(x.Created));
    if (messages.length > after) {
      const msg = await (await fetch(`${base}/api/v1/message/${messages[0].ID}`)).json();
      const link = String(msg.Text ?? "").match(/https?:\/\/\S+reset-password\?token=[\w-]+/)?.[0];
      if (link) return new URL(link).pathname + new URL(link).search;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No new set-password email for ${to}`);
}
