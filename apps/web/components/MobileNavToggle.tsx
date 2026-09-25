"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavItem } from "@/lib/navigation";

// The public header's primary nav (.main-nav) hides below 980px with no replacement --
// FRONTEND_ANALYSIS.md #4.1: the CSS already reserved a ".mobile-menu" slot for a toggle
// that was never built, so below that width the nav links were simply unreachable. This
// fills that slot: a toggle button revealing the same nav items in a dropdown panel.
// Reuses SiteHeader's own `nav` array -- no new nav data, no route/API change. An item
// with `children` (DesktopNav's hover/click dropdown on wider screens) renders here as
// the parent link followed by its children indented underneath -- no separate
// expand/collapse needed, since a vertical list can just show everything at once.
export default function MobileNavToggle({
  nav,
  buttonClassName = "mobile-menu",
  panelClassName = "mobile-nav-panel",
  panelId = "mobile-nav-panel",
}: {
  nav: NavItem[];
  buttonClassName?: string;
  panelClassName?: string;
  panelId?: string;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className={buttonClassName}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={open ? "menu-bars open" : "menu-bars"} aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </button>
      <nav id={panelId} className={panelClassName} aria-label="Primary" hidden={!open}>
        {nav.map((item) => (
          <div key={item.href} className="mobile-nav-group">
            <Link href={item.href} onClick={() => setOpen(false)} aria-current={pathname === item.href ? "page" : undefined}>
              {item.label}
            </Link>
            {item.children?.length ? (
              <div className="mobile-nav-subgroup">
                {item.children.map((child) => (
                  <Link key={child.href} href={child.href} onClick={() => setOpen(false)} aria-current={pathname === child.href ? "page" : undefined}>
                    {child.label}
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </nav>
    </>
  );
}
