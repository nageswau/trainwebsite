"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavItem } from "@/lib/navigation";

// The flat public nav had grown to 12 items (IT_PUBLIC) and was wrapping awkwardly --
// several multi-word labels breaking onto two lines -- at common desktop/laptop widths.
// Items with `children` (see lib/navigation.ts) now render as a hover/click dropdown
// instead of a flat top-level link, cutting the visible row down to a scannable count
// without dropping any destination.
export default function DesktopNav({ nav }: { nav: NavItem[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => setOpenIndex(null), [pathname]);

  useEffect(() => {
    if (openIndex === null) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenIndex(null);
    }
    function onPointerDown(event: MouseEvent) {
      if (navRef.current && !navRef.current.contains(event.target as Node)) setOpenIndex(null);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [openIndex]);

  return (
    <nav className="main-nav" ref={navRef}>
      {nav.map((item, index) =>
        item.children?.length ? (
          <div key={item.href} className="nav-dropdown" onMouseEnter={() => setOpenIndex(index)} onMouseLeave={() => setOpenIndex(null)}>
            <button
              type="button"
              className="nav-dropdown-trigger"
              aria-expanded={openIndex === index}
              aria-controls={`nav-dropdown-panel-${index}`}
              onClick={() => setOpenIndex(index)}
            >
              {item.label}
              <span className="nav-caret" aria-hidden="true">▾</span>
            </button>
            {openIndex === index && (
              // The visible card is a separate inner element from the hover/positioning
              // box (`.nav-dropdown-panel`) on purpose: `.nav-dropdown-panel` covers the
              // full gap down to the card, including the space that used to be a plain
              // CSS margin. A margin sits outside an element's own box, so a real mouse
              // moving through it (not a synthetic Playwright click, which teleports
              // straight to its target and never reproduced this) was leaving
              // `.nav-dropdown`'s hoverable area entirely mid-gap, firing `onMouseLeave`
              // and closing the menu before the cursor ever reached a submenu link.
              <div id={`nav-dropdown-panel-${index}`} className="nav-dropdown-panel">
                <div className="nav-dropdown-panel-inner">
                  {item.children.map((child) => (
                    <Link key={child.href} href={child.href}>
                      {child.label}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <Link key={item.href} href={item.href}>
            {item.label}
          </Link>
        )
      )}
    </nav>
  );
}
