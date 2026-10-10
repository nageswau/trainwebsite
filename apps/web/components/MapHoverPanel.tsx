"use client";

import { type ReactNode, type SyntheticEvent, useState } from "react";

// upc-025 (MP14): shows the four counts of the country under the pointer or keyboard focus. One delegated handler reads the hovered
// link's data attributes, so the server-rendered map stays out of the client bundle. Visual only (aria-hidden): each link's accessible
// name already carries the same counts.
type Shown = { name: string; partner: string; inProgress: string; target: string; lost: string };

function shownFrom(event: SyntheticEvent): Shown | null {
  const link = (event.target as Element).closest?.("[data-name]") as HTMLElement | SVGElement | null;
  if (!link) return null;
  const d = link.dataset;
  return { name: d.name ?? "", partner: d.partner ?? "0", inProgress: d.inProgress ?? "0", target: d.target ?? "0", lost: d.lost ?? "0" };
}

export default function MapHoverPanel({ children }: { children: ReactNode }) {
  const [shown, setShown] = useState<Shown | null>(null);
  const show = (event: SyntheticEvent) => setShown(shownFrom(event));
  return (
    <div className="world-map-frame" onMouseOver={show} onFocus={show} onMouseLeave={() => setShown(null)} onBlur={() => setShown(null)}>
      {children}
      <div className="map-panel" aria-hidden="true">
        {shown ? (
          <>
            <strong>{shown.name}</strong>
            <span><i className="map-swatch map-partner" /> {shown.partner} partner</span>
            <span><i className="map-swatch map-in_progress" /> {shown.inProgress} in progress</span>
            <span><i className="map-swatch map-target" /> {shown.target} target</span>
            <span><i className="map-swatch map-lost" /> {shown.lost} lost / closed</span>
          </>
        ) : (
          <span className="muted">Point at or tab to a country to see its counts; select it to open its universities.</span>
        )}
      </div>
    </div>
  );
}
