"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import type { NavItem } from "@/lib/navigation";

// AGN-008: a parent link with indented sub-links that differ only in their query string (the agency Applications filters). Only
// rendered for an item that has `children`, so every other portal's sidebar is unchanged.
function matches(href: string, pathname: string, params: URLSearchParams): boolean {
  const target = new URL(href, "http://nav.local");
  if (target.pathname !== pathname) return false;
  for (const [key, value] of target.searchParams) if (params.get(key) !== value) return false;
  return true;
}

export default function NavGroup({ item, pathname }: { item: NavItem; pathname: string }) {
  const params = useSearchParams();
  const children = item.children ?? [];
  const active = children.find((child) => matches(child.href, pathname, params));
  return (
    <>
      <Link href={item.href} aria-current={pathname === item.href && !active ? "page" : undefined}>
        {item.label}
      </Link>
      <ul className="portal-subnav" aria-label={`${item.label} filters`}>
        {children.map((child) => (
          <li key={child.href}>
            <Link href={child.href} aria-current={child === active ? "page" : undefined}>
              {child.label}
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
