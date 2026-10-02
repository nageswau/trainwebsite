"use client";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import type { NavItem } from "@/lib/navigation";

import MobileNavToggle from "./MobileNavToggle";
import { currentHref } from "./NavGroup";

// The portal top bar's mobile menu. AGN-008 QA8-08: when the menu holds query-string filters (the agency Applications children),
// the current item is the matching filter, else the plain path -- the sidebar's NavGroup rule. useSearchParams sits under Suspense;
// a menu without such items (every other portal) renders exactly as before, without reading the query.
const PANEL = { buttonClassName: "portal-mobile-menu", panelClassName: "portal-mobile-nav-panel", panelId: "portal-mobile-nav-panel" };

function WithFilters({ nav }: { nav: NavItem[] }) {
  const pathname = usePathname();
  const params = useSearchParams();
  return <MobileNavToggle nav={nav} {...PANEL} currentHref={currentHref(nav.map((item) => item.href), pathname, params)} />;
}

export default function PortalMobileNav({ nav }: { nav: NavItem[] }) {
  if (!nav.some((item) => item.href.includes("?"))) return <MobileNavToggle nav={nav} {...PANEL} />;
  return (
    <Suspense fallback={<MobileNavToggle nav={nav} {...PANEL} />}>
      <WithFilters nav={nav} />
    </Suspense>
  );
}
