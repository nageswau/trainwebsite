"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { MouseEvent, useState, useTransition } from "react";

import type { NavItem } from "@/lib/navigation";

// AGN-008: a parent link with indented sub-links that differ only in their query string (the agency Applications filters). Only
// rendered for an item that has `children`, so every other portal's sidebar is unchanged. Exported for the mobile menu (QA8-08).
export function matches(href: string, pathname: string, params: URLSearchParams): boolean {
  const target = new URL(href, "http://nav.local");
  if (target.pathname !== pathname) return false;
  for (const [key, value] of target.searchParams) if (params.get(key) !== value) return false;
  return true;
}

/** The href the menu marks as current: the matching child (path plus query), else the plain path (QA8-08, same rule as below). */
export function currentHref(hrefs: string[], pathname: string, params: URLSearchParams): string {
  return hrefs.find((href) => href.includes("?") && matches(href, pathname, params)) ?? pathname;
}

export default function NavGroup({ item, pathname }: { item: NavItem; pathname: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [clicked, setClicked] = useState<string | null>(null);
  const children = item.children ?? [];
  const active = children.find((child) => matches(child.href, pathname, params));

  // QA8-05: a plain left-click navigates in a transition so the link can show it is loading; the real href stays for new-tab clicks.
  function go(event: MouseEvent<HTMLAnchorElement>, href: string) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    setClicked(href);
    startTransition(() => router.push(href));
  }

  return (
    <>
      <Link href={item.href} aria-current={pathname === item.href && !active ? "page" : undefined}>
        {item.label}
      </Link>
      <ul className="portal-subnav" aria-label={`${item.label} filters`}>
        {children.map((child) => {
          const loading = pending && clicked === child.href;
          return (
            <li key={child.href}>
              <Link href={child.href} aria-current={child === active ? "page" : undefined} aria-busy={loading || undefined} onClick={(event) => go(event, child.href)}>
                {child.label}
                {loading && <span className="nav-loading"> Loading…</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}
