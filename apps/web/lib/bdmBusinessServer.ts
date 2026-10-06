import { serverApi } from "@/lib/api";
import { type Business, orgBusinessUrl } from "@/lib/bdmBusiness";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmBusiness.ts, which the client component imports.
/** bdm-021: the organization pages' Business section, read alongside the organization (the firstMou pattern). Never rejects: a
 * failure is null and the section offers "Try again"; a malformed id isn't sent. */
export function firstBusiness(id: string): Promise<Business | null> {
  return isUuid(id) ? serverApi<Business>(orgBusinessUrl(id)).catch(() => null) : Promise.resolve(null);
}
