import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { type Activity, orgActivitiesUrl } from "@/lib/bdmActivities";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmActivities.ts, which the client components import.
/** The organization pages' first timeline page, read alongside the organization (spec §6.2, §12.2 F2). It never rejects: a failure is
 * null and the section offers "Try again"; a malformed id isn't sent (the organization read answers "not found" for it). */
export function firstActivityPage(id: string): Promise<Page<Activity> | null> {
  return isUuid(id) ? serverApi<Page<Activity>>(orgActivitiesUrl(id)).catch(() => null) : Promise.resolve(null);
}
