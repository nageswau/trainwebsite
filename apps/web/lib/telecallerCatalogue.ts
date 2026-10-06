// tel-002 (DEC-SCOPE-074): the product/interest catalogue and campaign list -- types, labels, endpoints and the shared pickers'
// data source (the campaign form uses them now; tel-003's lead form reuses them). Labels are display only -- the API decides.
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import type { TelecallerTeam } from "@/lib/telecaller";

export type ProductGroup = "it" | "overseas" | "other";
export type Product = { id: string; group: ProductGroup; name: string; team: TelecallerTeam | null; program: { id: string; title: string } | null; active: boolean; sort_order: number };
export type Campaign = { id: string; name: string; source: string; product: { id: string; name: string; group: ProductGroup; active: boolean }; start_date: string; end_date: string | null; active: boolean };
export type ProgramOption = { id: string; title: string };

export const PRODUCTS_URL = "/api/v1/telecaller/products";
export const CAMPAIGNS_URL = "/api/v1/telecaller/campaigns";
export const CATALOGUE_PAGE_SIZE = 100;

export const GROUPS: ProductGroup[] = ["it", "overseas", "other"];
export const GROUP_LABEL: Record<ProductGroup, string> = { it: "IT Courses", overseas: "Overseas Education", other: "Other" };
// T18: an Other product with no team waits in the unassigned queue.
export const teamLabel = (team: TelecallerTeam | null) => (team === "it" ? "IT" : team === "overseas" ? "Overseas" : "Unassigned queue");

// EVID-019 §2, in source order (app/tel_sources.py).
export const SOURCE_LABEL: Record<string, string> = {
  instagram: "Instagram", facebook: "Facebook", google: "Google", website: "Website", whatsapp: "WhatsApp", walk_in: "Walk-in",
  college: "College", school: "School", agent: "Agent", referral: "Referral", exhibition_event: "Exhibition/Event", bdm: "BDM", other: "Other",
};
export const SOURCES = Object.keys(SOURCE_LABEL);

/** A campaign's dates as one phrase; date-only values are read in UTC so the day never shifts in the viewer's zone. */
export function campaignDates(c: Pick<Campaign, "start_date" | "end_date">): string {
  const start = formatDate(c.start_date, false, "UTC");
  return c.end_date ? `${start} – ${formatDate(c.end_date, false, "UTC")}` : `From ${start}`;
}

/** AC4 in the browser too (YYYY-MM-DD strings compare in date order); the API re-checks on the merged row. */
export const datesInOrder = (start: string, end: string | null) => !end || end >= start;

export async function getPage<T>(url: string, signal?: AbortSignal): Promise<Page<T>> {
  const response = await fetch(url, { signal });
  const body = await response.json().catch(() => null);
  if (!response.ok || !isPage<T>(body)) throw new Error(`Request failed (${response.status})`);
  return body;
}

/** The product picker: every active product, in catalogue order (the API orders them). It reads page after page (QA-01): a picker
 *  that stopped at the first 100 would silently hide the rest. */
export async function activeProducts(signal?: AbortSignal): Promise<Product[]> {
  const items: Product[] = [];
  for (;;) {
    const page = await getPage<Product>(`${PRODUCTS_URL}?active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}

/** The IT course link picker: the public list of active programs. */
export async function activePrograms(signal?: AbortSignal): Promise<ProgramOption[]> {
  const response = await fetch("/api/v1/public/programs", { signal });
  const body = await response.json().catch(() => null);
  if (!response.ok || !Array.isArray(body)) throw new Error(`Request failed (${response.status})`);
  return body.map((p: ProgramOption) => ({ id: p.id, title: p.title }));
}
