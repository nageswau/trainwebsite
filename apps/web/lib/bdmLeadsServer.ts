import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { type Lead, orgLeadsPageUrl } from "@/lib/bdmLeads";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmLeads.ts, which the client components import.
/** The organization pages' first lead page, read alongside the organization (bdm-009's firstActivityPage). It never rejects: a failure
 * is null and the section offers "Try again"; a malformed id isn't sent. */
export function firstLeadPage(id: string): Promise<Page<Lead> | null> {
  return isUuid(id) ? serverApi<Page<Lead>>(orgLeadsPageUrl(id)).catch(() => null) : Promise.resolve(null);
}
