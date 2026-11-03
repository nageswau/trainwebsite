"use client";
import { useEffect, useMemo, useState } from "react";

import { STAGES, stageLabel } from "@/lib/leadStages";

// itc-005 (DEC-SCOPE-362; API §12JH): the IT team's words, order and availability of the fixed lead and lifecycle statuses. IT lead
// screens read the catalogue here (the lead payloads keep the canonical status_label); lifecycle labels already arrive resolved from the
// API. Overseas leads always keep the defaults (E case). The API stays the authority: it refuses a turned-off stage (422) whatever the UI.

export const STATUS_LABELS_URL = "/api/v1/it/status-labels";
export const ADMIN_STATUS_LABELS_URL = "/api/v1/admin/it/status-labels";
export const statusLabelUrl = (kind: StatusKind, code: string) => `${ADMIN_STATUS_LABELS_URL}/${encodeURIComponent(kind)}/${encodeURIComponent(code)}`;

export type StatusKind = "lead" | "lifecycle";
export type StatusEntry = { code: string; label: string; default_label: string; sort_order: number; enabled: boolean; can_disable: boolean };
export type AdminStatusEntry = StatusEntry & { in_use: number; updated_at: string | null; updated_by: { id: string; full_name: string } | null };
export type StatusCatalogue<E extends StatusEntry = StatusEntry> = Record<StatusKind, E[]>;

const IT = "it";
let cached: StatusEntry[] | null = null; // the last IT lead catalogue, so the next screen does not flash the defaults
let inFlight: Promise<StatusEntry[] | null> | null = null;

/** Every mount asks again (a rename applies on the next navigation); concurrent mounts share one request. */
function loadLeadCatalogue(): Promise<StatusEntry[] | null> {
  inFlight ??= fetch(STATUS_LABELS_URL, { cache: "no-store" })
    .then(async (response) => (response.ok ? ((await response.json()) as StatusCatalogue).lead : null))
    .catch(() => null)
    .then((lead) => {
      inFlight = null;
      if (lead) cached = lead;
      return lead;
    });
  return inFlight;
}

/** After the IT Admin saves, drop the copy so this tab's next screen shows the new words. */
export function clearStatusLabels(): void {
  cached = null;
}

export type StageCatalogue = {
  /** The stage's words: the IT team's for an IT lead (or when no division is given on an IT screen), else the default. */
  label: (code: string, division?: string | null) => string;
  /** Filter options: every stage (a turned-off one still filters history), in the team's order. */
  stages: readonly (readonly [string, string])[];
  /** The stages the IT Admin turned off: pickers do not offer them. */
  off: ReadonlySet<string>;
};

const NONE: ReadonlySet<string> = new Set();
const DEFAULT_CATALOGUE: StageCatalogue = { label: (code) => stageLabel(code), stages: STAGES, off: NONE };

export function catalogueFrom(entries: StatusEntry[] | null): StageCatalogue {
  if (!entries) return DEFAULT_CATALOGUE;
  const words = new Map(entries.map((e) => [e.code, e.label]));
  return {
    label: (code, division) => (division && division !== IT ? stageLabel(code) : (words.get(code) ?? stageLabel(code))),
    stages: entries.map((e) => [e.code, e.label] as const),
    off: new Set(entries.filter((e) => !e.enabled).map((e) => e.code)),
  };
}

/** The IT lead stage catalogue once `active` has been true on this mount (an IT lead, or a list holding one -- so an empty filtered page
 *  keeps the IT words); the defaults before that, while loading, or when the read fails. */
export function useStageCatalogue(active: boolean): StageCatalogue {
  const [seen, setSeen] = useState(active);
  const [entries, setEntries] = useState<StatusEntry[] | null>(cached);
  if (active && !seen) setSeen(true);
  useEffect(() => {
    if (!seen) return;
    let live = true;
    void loadLeadCatalogue().then((lead) => live && lead && setEntries(lead));
    return () => {
      live = false;
    };
  }, [seen]);
  return useMemo(() => catalogueFrom(seen ? entries : null), [seen, entries]);
}
