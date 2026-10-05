import { mkdirSync } from "node:fs";
import path from "node:path";

import type { BrowserContext, Locator, Page } from "@playwright/test";

// Documentation screenshots (docs/documentation-plan.md S2.3). Saved to docs/screenshots/<module>/<file>.
const ROOT = path.resolve(__dirname, "../../../../docs/screenshots");
// School CRM set (docs/school-crm/documentation-plan.md S2.2): pass `root: SCHOOL_ROOT` to shoot().
export const SCHOOL_ROOT = path.resolve(__dirname, "../../../../docs/school-crm/screenshots");

// Every capture masks password inputs and the dev-only "Demo accounts" card (it prints the demo password).
// `center`: scroll that element to the middle of the viewport first (messages below a long form).
// `element`: capture just that element (a long form card), not the viewport -- note it in the screenshot index.
export async function shoot(
  page: Page,
  module: string,
  file: string,
  opts: { mask?: Locator[]; fullPage?: boolean; root?: string; center?: Locator; element?: Locator } = {},
) {
  const root = opts.root ?? ROOT;
  mkdirSync(path.join(root, module), { recursive: true });
  // Also masks the dev-only reset link on the forgot-password page (it carries a live reset token).
  const mask = [
    page.locator('input[type="password"]'),
    page.locator(".card", { hasText: "Demo accounts" }),
    page.getByText("Development only", { exact: false }),
    ...(opts.mask ?? []),
  ];
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
  const target = path.join(root, module, file);
  if (opts.element) {
    // Grow the viewport so the whole card fits below the sticky portal top bar, then restore it.
    const el = opts.element.first();
    const size = page.viewportSize() ?? { width: 1440, height: 900 };
    const box = await el.boundingBox();
    await page.setViewportSize({ width: size.width, height: Math.max(size.height, Math.ceil((box?.height ?? 0) + 240)) });
    await el.evaluate((node) => {
      const r = node.getBoundingClientRect();
      window.scrollTo({ top: Math.max(0, r.top + window.scrollY - (window.innerHeight - r.height) / 2), behavior: "instant" });
    });
    await el.screenshot({ path: target, mask, maskColor: "#C9CED6", animations: "disabled" });
    await page.setViewportSize(size);
    return;
  }
  if (opts.center) {
    await opts.center.first().evaluate((el) => {
      const r = el.getBoundingClientRect();
      window.scrollTo({ top: Math.max(0, r.top + window.scrollY - window.innerHeight / 2 + r.height / 2), behavior: "instant" });
    });
  }
  await page.screenshot({ path: target, mask, maskColor: "#C9CED6", fullPage: opts.fullPage ?? false, animations: "disabled" });
}

// The docs stacks on Docker Desktop leave some Next.js router *prefetch* streams open forever, which uses up the
// browser's 6 connections per host and stalls fonts/screenshots. Prefetches only speed up later navigation and
// change nothing on screen, so capture contexts drop them (School CRM S2).
export async function noPrefetch(target: BrowserContext | Page) {
  await target.route("**/*", (r) => (r.request().headers()["next-router-prefetch"] ? r.abort() : r.continue()));
}

// Passwords come from the shell, never from the repo: DOCS_PASSWORD (seeded accounts), DOCS_TEST_PASSWORD (accounts created for the docs).
export function password(kind: "seed" | "test" = "seed"): string {
  const value = kind === "seed" ? process.env.DOCS_PASSWORD : process.env.DOCS_TEST_PASSWORD;
  if (!value) throw new Error(kind === "seed" ? "Set DOCS_PASSWORD" : "Set DOCS_TEST_PASSWORD");
  return value;
}

// Scrolls an element to the top of the viewport (below the sticky header) before a capture.
export async function toTop(locator: Locator, offset = 80) {
  await locator.first().evaluate((el, off) => window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off, behavior: "instant" }), offset);
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

export async function mailLink(to: string, after = 0, pattern = /https?:\/\/\S+reset-password\?token=[\w-]+/): Promise<string> {
  const base = process.env.DOCS_MAILPIT_URL || "http://localhost:8025";
  for (let i = 0; i < 40; i++) {
    const list = await (await fetch(`${base}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
    const messages = [...(list.messages ?? [])].sort((x: { Created: string }, y: { Created: string }) => y.Created.localeCompare(x.Created));
    if (messages.length > after) {
      const msg = await (await fetch(`${base}/api/v1/message/${messages[0].ID}`)).json();
      const link = String(msg.Text ?? "").match(pattern)?.[0];
      if (link) return new URL(link).pathname + new URL(link).search;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No new matching email for ${to}`);
}

// School invite links (Coordinator → Principal/Teacher/Parent): /school/invite/<token>/accept.
export function inviteLink(to: string, after = 0): Promise<string> {
  return mailLink(to, after, /https?:\/\/\S+\/school\/invite\/[\w-]+\/accept/);
}
