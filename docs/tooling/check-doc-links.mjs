// Fails when a Markdown link or image under the documentation folders points at a missing file.
// Usage (repo root): node docs/tooling/check-doc-links.mjs
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const dirs = ["docs/user-manual", "docs/admin-manual", "docs/role-guides"];
const files = ["docs/faq.md", "docs/troubleshooting.md", "docs/screenshot-index.md"].filter(existsSync);
const walk = (d) =>
  existsSync(d)
    ? readdirSync(d).flatMap((f) => {
        const p = join(d, f);
        return statSync(p).isDirectory() ? walk(p) : p.endsWith(".md") ? [p] : [];
      })
    : [];

let bad = 0;
for (const f of [...dirs.flatMap(walk), ...files]) {
  for (const m of readFileSync(f, "utf8").matchAll(/\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
    const target = m[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    if (!existsSync(resolve(dirname(f), target))) {
      console.log(`${f}: missing ${target}`);
      bad++;
    }
  }
}
console.log(bad ? `${bad} broken link(s)` : "All links OK");
process.exit(bad ? 1 : 0);
