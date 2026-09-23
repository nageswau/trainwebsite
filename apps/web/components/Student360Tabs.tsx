"use client";

import { usePathname, useRouter } from "next/navigation";
import { Children, type KeyboardEvent, type ReactNode, useRef, useState } from "react";

import type { TabKey } from "@/lib/student360Links";

// ENH-013 -- WAI-ARIA tabs for the Student 360° view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §8).
// Only the selection lives here: the panels arrive already rendered by the server (Student360View), so this client component
// never needs a server-only import (tests/lib/clientBoundary.test.ts). Roving tabindex; arrows in both axes (the list is vertical
// on desktop and a scrolling row on mobile), Home/End; the choice is mirrored into ?tab= with replace + scroll:false so a deep link
// or reload lands on the same tab without a scroll jump.

export type TabSummary = { key: TabKey; label: string; status: "has_data" | "empty" | "restricted"; count: number | null };

const MOVES: Record<string, (i: number, last: number) => number> = {
  ArrowRight: (i, last) => (i === last ? 0 : i + 1),
  ArrowDown: (i, last) => (i === last ? 0 : i + 1),
  ArrowLeft: (i, last) => (i === 0 ? last : i - 1),
  ArrowUp: (i, last) => (i === 0 ? last : i - 1),
  Home: () => 0,
  End: (_i, last) => last,
};

// Spoken with the label, so a tab's state never depends on its colour alone.
function stateText(t: TabSummary): string {
  if (t.status === "restricted") return ", not available for your role";
  if (t.status === "empty") return ", no records yet";
  return t.count ? `, ${t.count} record${t.count === 1 ? "" : "s"}` : "";
}

export default function Student360Tabs({ tabs, initialTab, children }: { tabs: TabSummary[]; initialTab: TabKey; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const panels = Children.toArray(children);
  const [selected, setSelected] = useState(Math.max(0, tabs.findIndex((t) => t.key === initialTab)));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function select(index: number, moveFocus: boolean) {
    setSelected(index);
    router.replace(`${pathname}?tab=${tabs[index].key}`, { scroll: false });
    if (moveFocus) {
      const el = refs.current[index];
      el?.focus();
      el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    }
  }

  function onKeyDown(e: KeyboardEvent, index: number) {
    const move = MOVES[e.key];
    if (!move) return;
    e.preventDefault();
    select(move(index, tabs.length - 1), true);
  }

  return (
    <div className="s360-layout">
      <div role="tablist" aria-label="Student record sections" aria-orientation="vertical" className="s360-tablist">
        {tabs.map((t, i) => (
          <button
            key={t.key}
            ref={(el) => { refs.current[i] = el; }}
            id={`s360-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={i === selected}
            aria-controls="s360-panel"
            tabIndex={i === selected ? 0 : -1}
            className={`s360-tab ${t.status}`}
            onClick={() => select(i, false)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            <span>{t.label}</span>
            {t.status === "has_data" && t.count ? <span className="s360-count" aria-hidden="true">{t.count}</span> : null}
            {t.status === "restricted" ? <span className="s360-lock" aria-hidden="true">Restricted</span> : null}
            <span className="visually-hidden">{stateText(t)}</span>
          </button>
        ))}
      </div>
      <div id="s360-panel" role="tabpanel" aria-labelledby={`s360-tab-${tabs[selected].key}`} tabIndex={0} className="s360-panel">
        {panels[selected]}
      </div>
    </div>
  );
}
