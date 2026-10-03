"use client";

import { createContext } from "react";

import type { Trip } from "@/lib/bdmTravel";

// bdm-010 (QA10-16): the trip page's single source of truth. Every trip write returns the full updated trip (spec §12.1 A7), so a
// write applies that response here instead of asking the server to re-render -- two overlapping re-renders could land out of order
// and leave the page stale. `reload` re-reads the trip after a refusal (someone else changed it) and shows why at the top of the
// page -- the panel that was refused may close on the re-read (e.g. the editor once the trip is approved), taking its own message with it.
export type TripLive = { apply: (trip: Trip) => void; reload: (notice: string) => Promise<void> };

export const TripLiveContext = createContext<TripLive | null>(null);

export const isTrip = (data: unknown): data is Trip =>
  !!data && typeof data === "object" && typeof (data as Trip).code === "string" && Array.isArray((data as Trip).expenses);
